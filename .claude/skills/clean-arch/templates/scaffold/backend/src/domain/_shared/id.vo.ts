import { randomUUID } from "node:crypto";

export abstract class Id {
  protected constructor(private readonly rawValue: string) {}

  static generateValue(): string {
    return randomUUID();
  }

  equals(other: Id): boolean {
    return this.value === other.value;
  }

  get value(): string {
    return this.rawValue;
  }
}
