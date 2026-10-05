export abstract class AppError extends Error {
  abstract readonly code: string;
  abstract readonly status: number;
}

export class UnexpectedAppError extends AppError {
  readonly code = "unexpected";
  readonly status = 500;

  constructor(message: string) {
    super(message);
  }
}
