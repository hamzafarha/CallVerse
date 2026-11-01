import { AnimatePresence, ErrorBoundary, PageTransition } from "@callverse/shared";
import { Route, Routes, useLocation } from "react-router-dom";
import { CustomerProvider } from "./customer";
import Shell from "./layout/Shell";
import AccountPage from "./pages/Account";
import ChatPage from "./pages/Chat";
import DeskPage from "./pages/Desk";
import HelpPage from "./pages/Help";
import HomePage from "./pages/Home";

export default function App() {
  const location = useLocation();
  const section = location.pathname.split("/")[1] || "home";
  return (
    <CustomerProvider>
      <Shell>
        <AnimatePresence mode="wait">
          <PageTransition id={section} key={section}>
            <ErrorBoundary resetKey={location.pathname}>
              <Routes location={location}>
                <Route path="/" element={<HomePage />} />
                <Route path="/help" element={<HelpPage />} />
                <Route path="/help/:articleId" element={<HelpPage />} />
                <Route path="/account" element={<AccountPage />} />
                <Route path="/account/:contactId" element={<AccountPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/chat/:contactId" element={<ChatPage />} />
                <Route path="/desk" element={<DeskPage />} />
                <Route path="*" element={<HomePage />} />
              </Routes>
            </ErrorBoundary>
          </PageTransition>
        </AnimatePresence>
      </Shell>
    </CustomerProvider>
  );
}
