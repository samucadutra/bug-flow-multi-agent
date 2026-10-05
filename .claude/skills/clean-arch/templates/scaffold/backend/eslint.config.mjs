import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import js from "@eslint/js";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";

const rootDir = dirname(fileURLToPath(import.meta.url));

export default [
  {
    ignores: ["dist/**", "node_modules/**", "eslint.config.mjs"],
  },
  js.configs.recommended,
  {
    files: ["**/*.ts"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 2023,
        project: "./tsconfig.json",
        sourceType: "module",
        tsconfigRootDir: rootDir,
      },
      globals: {
        Buffer: "readonly",
        console: "readonly",
        process: "readonly",
        setImmediate: "readonly",
        setTimeout: "readonly",
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
    },
    rules: {
      ...tsPlugin.configs["recommended-type-checked"].rules,
      "max-classes-per-file": ["error", 1],
      "@typescript-eslint/explicit-member-accessibility": [
        "error",
        { accessibility: "no-public" },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          caughtErrorsIgnorePattern: "^_",
        },
      ],
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unsafe-assignment": "warn",
      "@typescript-eslint/no-unsafe-member-access": "warn",
      "@typescript-eslint/no-unsafe-call": "warn",
      "@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports" }],
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["../*"],
              message: "Use absolute imports (@/...) instead of deep relative imports.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/**/*.ts"],
    ignores: ["src/config/env.ts"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "MemberExpression[object.name='process'][property.name='env']",
          message:
            "process.env is forbidden outside src/config/env.ts. Read config there and inject values via constructor.",
        },
      ],
    },
  },
  {
    files: ["src/domain/**/*.ts"],
    ignores: ["**/*.spec.ts"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "MethodDefinition[kind='set']",
          message:
            "Setters are forbidden in domain/. Use a domain-named method instead.",
        },
      ],
    },
  },
  {
    files: ["src/infra/http/**/*.handler.ts"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "TryStatement",
          message:
            "try/catch is forbidden in handlers. Let exceptions propagate to the central error handler.",
        },
      ],
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/infra/repository/*", "@/infra/queries/*", "@/infra/gateway/*"],
              message:
                "Handlers may not import repositories, queries, or gateways. They receive use cases via constructor.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["src/usecase/**/*.ts"],
    ignores: ["**/*.spec.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/infra/*", "../infra/*", "../../infra/*"],
              message:
                "usecase/ may not import from infra/. Depend on interfaces from domain/.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["**/errors.ts", "**/*.spec.ts"],
    rules: {
      "max-classes-per-file": "off",
    },
  },
  {
    files: ["**/*.spec.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unsafe-assignment": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/no-unsafe-call": "off",
      "no-restricted-imports": "off",
    },
  },
];
