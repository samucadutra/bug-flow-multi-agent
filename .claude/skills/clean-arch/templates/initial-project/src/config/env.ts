import { z } from 'zod';

const schema = z.object({
  port:     z.coerce.number().int().min(1).max(65535).default(3000),
  logLevel: z.enum(['debug', 'info', 'warn', 'error']).default('info'),
  // Add project-specific env vars here:
  // databaseUrl:   z.string().url(),
  // sessionSecret: z.string().min(32),
});

const parsed = schema.safeParse({
  port:     process.env['PORT'],
  logLevel: process.env['LOG_LEVEL'],
});

if (!parsed.success) {
  console.error('Invalid environment configuration:', parsed.error.flatten());
  process.exit(1);
}

export const config = Object.freeze(parsed.data);
// Add `export type Config = typeof config;` when other modules need to type the config object.
