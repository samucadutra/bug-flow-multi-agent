"""Service layer conventions.

- Services take a session (or an engine / session factory for administrative operations) plus
  typed inputs, and return Pydantic models. They never return ORM objects.
- Bug services flush and never commit: the caller owns the transaction. Administrative
  operations and the run recorder manage their own transactions.
- Business rules live only in `bugflow.services`. The CLI and the future API call them and
  contain no logic of their own.
- Errors derive from `bugflow.services.errors.ServiceError`. Messages are fixed English text
  that never contains secrets, connection URLs or offending input values.
"""
