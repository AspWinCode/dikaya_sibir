// @ts-check
import js from "@eslint/js";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import tsParser from "@typescript-eslint/parser";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  { ignores: ["dist", "dist-editor", "dist-runtime", "node_modules", "coverage"] },
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parser: tsParser,
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { window: "readonly", document: "readonly", navigator: "readonly", console: "readonly", FormData: "readonly", File: "readonly", fetch: "readonly", localStorage: "readonly", sessionStorage: "readonly", URL: "readonly", URLSearchParams: "readonly", crypto: "readonly", setTimeout: "readonly", clearTimeout: "readonly", setInterval: "readonly", clearInterval: "readonly", HTMLElement: "readonly", HTMLInputElement: "readonly", HTMLDivElement: "readonly", HTMLTextAreaElement: "readonly", HTMLButtonElement: "readonly", KeyboardEvent: "readonly", MouseEvent: "readonly", React: "readonly" },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      react,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // New JSX transform — no need to import React in every file.
      "react/react-in-jsx-scope": "off",
      "react/jsx-uses-react": "off",
      // no-undef is unreliable with TS types/ambient globals; tsc already
      // catches genuine undefined-reference bugs with full type info.
      "no-undef": "off",
      // TypeScript (via tsc --noEmit, run separately) already enforces this
      // more precisely, including unused destructured props.
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/no-explicit-any": "off",
      "react/prop-types": "off",
      // `cond ? doA() : doB()` used for its side effect (no value is read)
      // is a deliberate, recurring style in this codebase — not a bug.
      "@typescript-eslint/no-unused-expressions": [
        "error",
        { allowTernary: true, allowShortCircuit: true },
      ],
    },
  },
];
