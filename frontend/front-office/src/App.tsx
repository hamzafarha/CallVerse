import { AnimatePresence, ErrorBoundary, PageTransition } from "@callverse/shared";
import { Route, Routes, useLocation } from "react-router-dom";
import { CustomerProvider } from "./customer";
import Shell from "./layout/Shell";
import AccountPage from "./pages/Account";
import ChatPage from "./pages/Chat";
import DeskPage from "./pages/Desk";
import HelpPage from "./pages/Help";
import HomePage from "./pages/Home";

/**
 * The page routes of the front office. Each URL path shows one page inside the Shell (header + footer).
 * CustomerProvider shares the demo customer with every page.
 */
export default function App() {
  const location = useLocation();
  // First part of the path ("chat", "help", ...): when it changes, the page transition plays.
  const section = location.pathname.split("/")[1] || "home";
  return (
    <CustomerProvider>
      <Shell>
        {/* mode="wait": the old page finishes fading out before the new one comes in. */}
        <AnimatePresence mode="wait">
          <PageTransition id={section} key={section}>
            {/* A crash in one page shows an error box instead of a blank screen; changing page resets it. */}
            <ErrorBoundary resetKey={location.pathname}>
              <Routes location={location}>
                {/* :articleId and :contactId are URL parameters (e.g. /chat/SC000014 opens a chat as that
                   customer). */}
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
