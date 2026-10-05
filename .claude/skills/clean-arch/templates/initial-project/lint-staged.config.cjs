/**
 * lint-staged config — runs the fast gates (1–2) on staged TS files.
 * Mounted by the pre-commit hook in .husky/pre-commit.
 */
module.exports = {
  '*.ts': [
    'eslint --max-warnings=0',
    () => 'tsc --noEmit -p tsconfig.json',
  ],
};
