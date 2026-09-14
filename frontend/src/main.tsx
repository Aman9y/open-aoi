import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { InspectPage } from "./pages/InspectPage";
import { HistoryPage } from "./pages/HistoryPage";
import { ReferencesPage } from "./pages/ReferencesPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/inspect" replace /> },
      { path: "inspect", element: <InspectPage /> },
      { path: "history", element: <HistoryPage /> },
      { path: "references", element: <ReferencesPage /> },
      { path: "analytics", element: <AnalyticsPage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
