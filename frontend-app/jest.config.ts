import type { Config } from 'jest';
import nextJest from 'next/jest';

const createJestConfig = nextJest({
  dir: './',
});

const config: Config = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.ts'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
  },
  testPathIgnorePatterns: ['<rootDir>/.next/', '<rootDir>/node_modules/'],
};

// ESM-only packages that need to be transformed by Jest.
// Uses prefix patterns to keep the list compact.
const ESM_PATTERNS = [
  'react-markdown',
  'remark-.*',
  'unified',
  'bail',
  'trough',
  'vfile.*',
  'devlop',
  'unist-.*',
  'hast-.*',
  'estree-.*',
  'property-information',
  'space-separated-tokens',
  'comma-separated-tokens',
  'mdast-.*',
  'micromark.*',
  'trim-lines',
  'ccount',
  'escape-string-regexp',
  'markdown-table',
  'longest-streak',
  'zwitch',
  'decode-named-character-reference',
  'character-entities.*',
  'character-reference-invalid',
  'is-plain-obj',
  'is-alphabetical',
  'is-alphanumerical',
  'is-decimal',
  'is-hexadecimal',
  'html-url-attributes',
  'parse-entities',
  'stringify-entities',
].join('|');

// next/jest overrides transformIgnorePatterns, so we merge after resolution
const jestConfigFn = createJestConfig(config);

export default async function () {
  const resolved = await jestConfigFn();
  resolved.transformIgnorePatterns = [
    `node_modules/(?!(${ESM_PATTERNS})/)`,
  ];
  return resolved;
}
