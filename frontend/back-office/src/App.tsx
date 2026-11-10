import { AnimatePresence, ErrorBoundary, PageTransition } from "@callverse/shared";
import { Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import AgentsPage from "./pages/Agents";
import CentrePage from "./pages/Centre";
import DataPage from "./pages/Data";
import ForecastPage from "./pages/Forecast";
import MlopsPage from "./pages/Mlops";
import OverviewPage from "./pages/Overview";
import TwinPage from "./pages/Twin";
import WorkforcePage from "./pages/Workforce";

/**
 * The pages of the back office (control room), one per URL path, inside the Layout (sidebar + top bar). The
 * sections follow the project's layers: data, simulation and forecasting, agents, serving and
 * MLOps. The contact centre (/centre) fills the whole screen, without the sidebar.
 */
export default function App() {
  const location = useLocation();
  // The contact centre looks like its own app on a projector: no sidebar, no top bar.
  if (location.pathname.startsWith("/centre"))
    return (
      <ErrorBoundary resetKey={location.pathname}>
        <CentrePage />
      </ErrorBoundary>
    );
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
              <Route path="/mlops" element={<MlopsPage />} />
              <Route path="*" element={<OverviewPage />} />
            </Routes>
          </ErrorBoundary>
        </PageTransition>
      </AnimatePresence>
    </Layout>
  );
}
