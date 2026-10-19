import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import "./index.css";
import AgentsPage from "./pages/Agents";
import DataPage from "./pages/Data";
import EvaluationPage from "./pages/Evaluation";
import ForecastPage from "./pages/Forecast";
import MlopsPage from "./pages/Mlops";
import OverviewPage from "./pages/Overview";
import QualityPage from "./pages/Quality";
import TwinPage from "./pages/Twin";
import WorkforcePage from "./pages/Workforce";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/forecast" element={<ForecastPage />} />
          <Route path="/twin" element={<TwinPage />} />
          <Route path="/workforce" element={<WorkforcePage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/quality" element={<QualityPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/mlops" element={<MlopsPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  </React.StrictMode>,
);
