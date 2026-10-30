import js from '@eslint/js'
import ts from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

export default ts.config(
  { ignores: ['out/**', 'node_modules/**'] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...vue.configs['flat/recommended'],
  { files: ['**/*.vue'], languageOptions: { parserOptions: { parser: ts.parser } }, rules: { 'no-undef': 'off' } },
  { files: ['tests/*.cjs'], languageOptions: { globals: { require: 'readonly', __dirname: 'readonly', clearTimeout: 'readonly' } }, rules: { '@typescript-eslint/no-require-imports': 'off' } },
  { languageOptions: { globals: { window: 'readonly', document: 'readonly', fetch: 'readonly', console: 'readonly', URL: 'readonly', AbortSignal: 'readonly', process: 'readonly', setTimeout: 'readonly' } }, rules: { 'vue/html-self-closing': 'off', 'vue/max-attributes-per-line': 'off', 'vue/singleline-html-element-content-newline': 'off', 'vue/html-closing-bracket-newline': 'off' } }
)
