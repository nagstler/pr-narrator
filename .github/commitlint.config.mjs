// Conventional Commits config for wagoid/commitlint-github-action.
// Allowed types must stay in sync with the commitizen setup in pyproject.toml.
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'chore',
        'docs',
        'refactor',
        'test',
        'ci',
        'perf',
        'build',
        'style',
        'revert',
      ],
    ],
  },
};
