import React from "react";
import { createRoot } from "react-dom/client";
import "./design/folio.css";
import App from "./platform/App.jsx";

createRoot(document.getElementById("root")).render(<App />);
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
