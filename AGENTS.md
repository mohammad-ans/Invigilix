# Working in the exam repository

1. Read `docs/requirements.md`, `docs/pages.md`, `docs/theme.md`, and `contracts/attempt-api.md`. The owner and allowed paths for this branch are in `collaboration/ownership.json`. State the branch, SRS IDs, screens and acceptance cases before editing.
2. Implement inside the assigned feature's frontend, FastAPI and test directories. The platform maintainer owns shared routing, migrations, dependencies, design primitives, API contracts and integration. Honor the SRS security rules in every feature.
3. For a missing field, component or permission, describe the smallest shared change in the issue or PR. The maintainer can land it in a foundation PR. Continue independent work using fixtures that match the approved contract.
4. Import shared tokens and components. The page inventory specifies each page's hierarchy, states and ownership. Match the reference at desktop and 360 CSS px. Use real labels and icons alongside semantic color.
5. In the PR, map changes to SRS and acceptance IDs, list tests run, and include screenshots for UI changes. Keep the preview and real API paths distinct. Request integration after the feature passes its own tests.
