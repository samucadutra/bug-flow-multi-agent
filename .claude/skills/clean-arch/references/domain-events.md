# Domain events

Deep dive on when to use domain events, the `DomainEvent` and `EventBus` shapes, and event handlers in `infra/event-handlers/`. Read alongside `SKILL.md` rule 11 (DI by constructor) and `domain-modeling.md` (aggregate boundaries).

Domain events are **opt-in**. Most apps work fine without them. Adopt them when you need:

1. **Cross-aggregate side effects** without a shared transaction ("when a video is processed, notify the user").
2. **Decoupling between features** ("when a user is suspended, archive their videos" — User feature emits, Video feature reacts, no direct dependency).
3. **A natural extension point** for future subscribers without changing the originating use case.

If none of those apply, do not introduce events. The complexity is real.

---

## 1. The shapes

`DomainEvent` is a marker abstract class; specific events extend it. `EventBus` is the publishing interface.

```ts
// domain/_shared/event.ts
export abstract class DomainEvent {
  readonly occurredAt = new Date();
  abstract readonly name: string;
}

export interface EventBus {
  publish(event: DomainEvent): Promise<void>;
  publishAll(events: DomainEvent[]): Promise<void>;
}
```

Per-feature events live in `domain/<feature>/events.ts`:

```ts
// domain/video/events.ts
import { DomainEvent } from '@/domain/_shared/event';

export class VideoUploaded extends DomainEvent {
  readonly name = 'video.uploaded';
  constructor(public readonly videoId: string, public readonly userId: string) { super(); }
}

export class VideoProcessingCompleted extends DomainEvent {
  readonly name = 'video.processing-completed';
  constructor(public readonly videoId: string) { super(); }
}

export class VideoProcessingFailed extends DomainEvent {
  readonly name = 'video.processing-failed';
  constructor(public readonly videoId: string, public readonly reason: string) { super(); }
}
```

Conventions:

- One `events.ts` per feature.
- Class name describes what happened, in past tense: `VideoUploaded`, not `UploadVideo`.
- `name` is dotted-lower-kebab: `video.uploaded`, `user.suspended`.
- Constructor parameters carry the IDs and minimum data subscribers need. Do **not** include the full entity — events travel and serialize; they should be small and stable.

---

## 2. Publishing — from the use case, never from the entity

This is the most important rule. Publish from the use case after the relevant write commits. Never from the entity.

```ts
// usecase/video/upload-video.usecase.ts
import { VideoUploaded } from '@/domain/video/events';

export class UploadVideoUseCase {
  constructor(
    private readonly videoRepo: VideoRepository,
    private readonly storage: StorageGateway,
    private readonly events: EventBus,
  ) {}

  async execute(input) {
    const stored = await this.storage.store(input.file, input.filename);
    const video = Video.create({ userId: input.actorId, filename: input.filename, sizeBytes: input.sizeBytes, storageKey: stored.key });
    await this.videoRepo.save(video);

    await this.events.publish(new VideoUploaded(video.id, input.actorId));

    return toOutput(video);
  }
}
```

### Why not from the entity

Some popular tactical-DDD writeups have entities collect events internally (`user.events: DomainEvent[]`) and the repository drains them on `save`. The skill rejects this pattern because:

- **Entities become I/O-aware.** They start "remembering" what happened to them, which is state about the application's history, not the domain.
- **Order of mutations matters at the wrong layer.** If `user.suspend()` enqueues `UserSuspended` and then a use case calls `user.changeEmail()` after, the event order leaks implementation detail.
- **TypeScript's lack of effects makes it easy to forget to drain.** Other languages can mark methods as event-emitting; in TS, it is convention only, and conventions break.

The skill's rule: **the use case is the boundary**. It mutates, saves, then publishes. Order is explicit; no draining; no implicit state on entities.

### Publishing multiple events

Use `publishAll` when several events arise from one operation:

```ts
const videoEvents = [new VideoProcessingStarted(video.id), new VideoStageEntered(video.id, 'transcribing')];
await this.events.publishAll(videoEvents);
```

If the events are published as part of a database transaction (transactional outbox pattern), `publishAll` is implemented to enqueue them within the transaction so they are atomic with the write. See section 5.

---

## 3. Subscribing — event handlers in `infra/event-handlers/`

Subscribers live in `infra/event-handlers/`, organized by the feature that **reacts** (not by the feature that emits).

```
infra/event-handlers/
  notification/
    notify-user-on-video-completed.handler.ts        # reacts to video.processing-completed
    notify-user-on-video-failed.handler.ts
  video/
    archive-videos-on-user-suspended.handler.ts      # reacts to user.suspended (cross-feature reaction)
```

Each handler is a class with a single method that processes one event type. Same shape as HTTP handlers and worker jobs:

```ts
// infra/event-handlers/notification/notify-user-on-video-completed.handler.ts
import type { VideoProcessingCompleted } from '@/domain/video/events';
import type { SendNotificationUseCase } from '@/usecase/notification/send-notification.usecase';

export class NotifyUserOnVideoCompletedHandler {
  constructor(private readonly sendNotification: SendNotificationUseCase) {}

  async handle(event: VideoProcessingCompleted): Promise<void> {
    await this.sendNotification.execute({
      kind: 'video.completed',
      videoId: event.videoId,
    });
  }
}
```

Each handler:
- Implements one method (commonly `handle(event)`).
- Receives use cases via constructor, not repositories directly. Use cases stay the unit of business work; handlers are thin wiring.
- Is registered in the composition root (see section 4).

The handler's class name reads as a sentence: `<Verb><Object>On<EventName>Handler`. `NotifyUserOnVideoCompletedHandler`, `ArchiveVideosOnUserSuspendedHandler`.

---

## 4. Wiring in the composition root

```ts
// main.ts (excerpt)
import { InMemoryEventBus } from './infra/event-handlers/in-memory-event-bus';
import { NotifyUserOnVideoCompletedHandler } from './infra/event-handlers/notification/notify-user-on-video-completed.handler';
import { ArchiveVideosOnUserSuspendedHandler } from './infra/event-handlers/video/archive-videos-on-user-suspended.handler';

const events = new InMemoryEventBus();

const notifyOnCompleted = new NotifyUserOnVideoCompletedHandler(sendNotification);
const archiveOnSuspended = new ArchiveVideosOnUserSuspendedHandler(archiveVideos);

events.subscribe('video.processing-completed', (e) => notifyOnCompleted.handle(e));
events.subscribe('user.suspended', (e) => archiveOnSuspended.handle(e));

const uploadVideo = new UploadVideoUseCase(videoRepo, storage, events);
```

The composition root explicitly wires every subscription. There is no auto-discovery, no decorator scanning. If a handler is not subscribed in `main.ts`, it does not run. This makes the event topology readable in one place.

---

## 5. Implementations

### `InMemoryEventBus`

For most apps, the in-process bus is enough. It dispatches events synchronously inside the same Node.js process.

```ts
// infra/event-handlers/in-memory-event-bus.ts
import type { EventBus } from '@/domain/_shared/event';
import type { DomainEvent } from '@/domain/_shared/event';

type Subscriber = (event: DomainEvent) => Promise<void>;

export class InMemoryEventBus implements EventBus {
  private readonly subscribers = new Map<string, Subscriber[]>();

  subscribe(eventName: string, sub: Subscriber): void {
    const list = this.subscribers.get(eventName) ?? [];
    list.push(sub);
    this.subscribers.set(eventName, list);
  }

  async publish(event: DomainEvent): Promise<void> {
    const subs = this.subscribers.get(event.name) ?? [];
    await Promise.all(subs.map((s) => s(event)));
  }

  async publishAll(events: DomainEvent[]): Promise<void> {
    for (const e of events) await this.publish(e);
  }
}
```

Trade-offs:
- **In-process**: subscribers run in the same request lifecycle. Side effects happen before `publish` returns.
- **No persistence**: if a subscriber throws, the event is lost (other subscribers may still have run depending on the implementation).
- **No retries**: errors propagate. Use case caller sees them.

This is acceptable for small apps where event handlers are short, idempotent, and not critical to operate. For more, use the outbox pattern below.

### Transactional outbox (for stronger guarantees)

When events must be published reliably even on transient subscriber failures, store them in an outbox table within the same transaction as the write. A separate process drains the outbox and publishes to a real bus (Redis Streams, Kafka, RabbitMQ) with retries.

```
1. Use case: write entity + insert event row → COMMIT (atomic)
2. Outbox dispatcher (separate process): read pending events, publish to bus, mark dispatched
3. Subscribers (separate processes): consume from bus, handle, ack
```

The skill's `domain/` does not change in this case. The `EventBus` implementation in `infra/` is what changes (the in-memory bus becomes a `OutboxEventBus` that writes to the DB inside the current transaction context).

This is **opt-in and rare**. Adopt only when you have evidence of needing the guarantees: events that trigger paid actions, regulatory reporting, anything where loss is unacceptable. For most apps, the in-memory bus is sufficient.

---

## 6. When NOT to use events

Do not use domain events for:

- **Synchronous coordination within one aggregate write.** Use a single use case with `UnitOfWork` if you need atomicity across two aggregates that genuinely belong together. Events are for *eventual* consistency.
- **Replacing direct calls in clear-flow logic.** If `UploadVideoUseCase` directly needs a thumbnail extracted, that is a synchronous step in the use case (not an event). Use events only when the reaction is genuinely separate concerns.
- **Cross-feature dependencies that should be one feature.** If two aggregates "always" react to each other and never independently, they may be one aggregate. See `domain-modeling.md`.

The litmus test: **if the publisher must wait for the subscriber to succeed, it is not an event — it is a synchronous call.** Events represent things that happened; subscribers react in their own time.

---

## 7. Common pitfalls

| Pitfall                                                          | Fix                                                          |
|------------------------------------------------------------------|--------------------------------------------------------------|
| Entity collecting events internally; repo draining on `save`     | Move publishing to the use case                              |
| Publishing before the write commits                              | Publish after `save` (or via outbox inside the transaction)  |
| Subscriber that depends on side effects of another subscriber    | Subscribers should be independent; do not rely on order      |
| Handler doing complex business logic directly                    | Delegate to a use case; the handler is wiring                |
| Adding events for synchronous coordination ("call A then call B") | Use a single use case with method calls                     |
| Auto-discovery / decorator-based subscription                    | Wire explicitly in the composition root                      |
| Events with the full entity payload                              | Events carry IDs and minimal data; subscribers re-fetch       |
| Catching event errors silently in the publisher                  | Decide explicitly: in-memory bus throws, outbox persists     |
| `domain/<feature>/events.ts` importing from `infra/`             | Events are pure data; no I/O imports                          |

---

## Cross-references

- **`SKILL.md` rules**: 5 (`event.ts` joins the `_shared` whitelist when adopted), 9 (domain may import only validation/date/numeric libs — events are pure data), 11 (DI by constructor — `EventBus` is injected like any other dependency).
- **`anti-patterns.md`**: A11 (use case with multiple methods — events should not be a workaround), A14 (invariant in use case — domain rule belongs on the entity, not as event side effect).
- **`use-case-pattern.md`**: section 6 (UoW for synchronous atomicity vs events for eventual consistency).
- **`domain-modeling.md`**: aggregate boundaries determine when events are needed.
- **`composition-root.md`**: where the event bus and handlers are wired.
- **`cross-feature-use-cases.md`**: alternative to events when a primary aggregate makes the synchronous flow simple.
