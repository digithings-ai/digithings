declare module "@assistant-ui/react-markdown/styles/dot.css";

// WS4: moved skins import the package stylesheets via relative side-effect
// imports. The app got its `*.css` declarations from Next's global types;
// the package needs its own.
declare module "*.css";
