import { AnimatePresence, ErrorBoundary, PageTransition } from "@callverse/shared";
import { Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import AgentsPage from "./pages/Agents";
import DataPage from "./pages/Data";
import EvaluationPage from "./pages/Evaluation";
import ForecastPage from "./pages/Forecast";
import MlopsPage from "./pages/Mlops";
import OverviewPage from "./pages/Overview";
import QualityPage from "./pages/Quality";
import TwinPage from "./pages/Twin";
import WorkforcePage from "./pages/Workforce";

/**
 * The pages of the back office (control room), one per URL path, inside the Layout (sidebar + top bar). The
 * sections follow the project's layers: data, simulation and forecasting, agents, evaluation, serving and
 * MLOps.
 */
export default function App() {
  const location = useLocation();
  return (
    <Layout>
      {/* mode="wait": the old page fades out before the new one comes in. A crash in one page shows an
         error box; changing page resets it. */}
      <AnimatePresence mode="wait">
        <PageTransition id={location.pathname} key={location.pathname}>
          <ErrorBoundary resetKey={location.pathname}>
            <Routes location={location}>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/data" element={<DataPage />} />
              <Route path="/forecast" element={<ForecastPage />} />
              <Route path="/twin" element={<TwinPage />} />
              <Route path="/workforce" element={<WorkforcePage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/quality" element={<QualityPage />} />
              <Route path="/evaluation" element={<EvaluationPage />} />
              <Route path="/mlops" element={<MlopsPage />} />
              <Route path="*" element={<OverviewPage />} />
            </Routes>
          </ErrorBoundary>
        </PageTransition>
      </AnimatePresence>
    </Layout>
  );
}
