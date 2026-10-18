# FC Ops frontend

## UI design system

All styling lives in `src/index.css` (tokens on `:root`, then components); all shared
React primitives live in `src/components/ui.jsx`. New screens should be assembled from
these instead of ad-hoc markup or inline styles.

- **Tokens**: colours (`--accent`, `--ok/warn/bad` + `-soft`), spacing `--space-*`,
  radii `--radius*`, shadows `--shadow*`. Change a token, not a component.
- **Page**: start every page with `<PageHeader title subtitle meta actions />`.
- **Surfaces**: `<Card title subtitle actions footer flush tabs as="form">`. Use `flush`
  for tables, `footer` for form submit buttons, `className="filter-bar"` for filter rows.
- **Data**: `<StatCard label value tone hint icon />`, `<Meter />`, `<Tabs />`, `<Tag tone />`,
  `<StatusTag />`, `<SeverityTag />`.
- **Feedback**: `<Banner kind>` for errors/notices, `<Empty title icon>` for empty states.
- **Loading**: never show "Loading…" text. Use `<Loading />` (table skeleton, or
  `variant="text"`), `<SkeletonCard />`, or `<PageSkeleton stats split />` for whole pages.
- **Buttons**: native `<button>` / `<Link className="btn">`; modifiers `secondary`,
  `danger`, `ok`, `link`, `sm`, `icon-btn`.
- **Icons**: `<Icon name>` from the inline set in `ui.jsx`; add a path there rather than
  adding an icon dependency.

## Vite template notes

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
