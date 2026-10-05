import { randomUUID } from 'node:crypto';
import { InvalidIdError } from './errors';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Base ID value object. Feature-specific IDs extend this:
 *
 *   export class UserId extends Id {
 *     static override generate(): UserId { return new UserId(super.generate().value); }
 *     static override from(value: string): UserId { return new UserId(super.from(value).value); }
 *   }
 *
 * Subclassing (rather than branded types) makes `equals` distinguish
 * between same-string IDs of different types at runtime.
 */
export class Id {
  readonly value: string;

  protected constructor(value: string) {
    this.value = value;
  }

  static generate(): Id {
    return new Id(randomUUID());
  }

  static from(value: string): Id {
    if (!UUID_RE.test(value)) throw new InvalidIdError(value);
    return new Id(value);
  }

  equals(other: Id): boolean {
    return this.value === other.value && this.constructor === other.constructor;
  }
}
