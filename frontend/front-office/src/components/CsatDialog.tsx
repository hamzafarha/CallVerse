import { AnimatePresence, motion } from "@callverse/shared";
import { Star } from "lucide-react";
import { useState } from "react";

const WORDS = ["", "Very poor", "Poor", "Okay", "Good", "Excellent"];

/** Post-chat survey: 1-5 stars (the CSAT of BO2). */
export function CsatDialog({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (csat?: number) => void }) {
  const [hover, setHover] = useState(0);
  const [value, setValue] = useState(0);
  const shown = hover || value;
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, y: 20, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: "spring", bounce: 0.3 }}
            className="card w-full max-w-sm p-6 text-center shadow-lift"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-xl font-semibold text-ink">How did we do?</h3>
            <p className="mt-1 text-sm text-muted">Your rating is the CSAT the twin uses for BO2.</p>
            <div className="mt-5 flex justify-center gap-1.5" onMouseLeave={() => setHover(0)}>
              {[1, 2, 3, 4, 5].map((n) => (
                <motion.button
                  key={n}
                  whileHover={{ scale: 1.2, rotate: -8 }}
                  whileTap={{ scale: 0.9 }}
                  onMouseEnter={() => setHover(n)}
                  onClick={() => setValue(n)}
                  aria-label={`${n} stars`}
                >
                  <Star
                    size={34}
                    className="transition-colors"
                    style={{ color: n <= shown ? "var(--warning)" : "var(--baseline)", fill: n <= shown ? "var(--warning)" : "transparent" }}
                  />
                </motion.button>
              ))}
            </div>
            <div className="mt-2 h-5 text-sm font-medium text-ink2">{WORDS[shown]}</div>
            <div className="mt-5 flex gap-2">
              <button className="btn btn-ghost flex-1" onClick={() => onSubmit(undefined)}>
                Skip
              </button>
              <button className="btn btn-primary flex-1" disabled={!value} onClick={() => onSubmit(value)}>
                Send rating
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
