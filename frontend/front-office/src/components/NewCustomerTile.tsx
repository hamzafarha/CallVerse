/**
 * The "Create a new customer" tile, shown first among the demo customers (home page and sign-in picker).
 */
import { Spotlight, motion } from "@callverse/shared";
import { ArrowRight, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";

export function NewCustomerTile() {
  return (
    <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45 }}>
      <Link to="/account/new" className="group block h-full">
        <Spotlight className="card card-hover flex h-full min-h-[220px] flex-col items-center justify-center border-dashed p-5 text-center">
          <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl gradient-brand text-white shadow-glow transition-transform group-hover:scale-110">
            <UserPlus size={22} />
          </div>
          <div className="font-semibold text-ink">Create a new customer</div>
          <p className="mt-1 max-w-[220px] text-xs leading-relaxed text-ink2">
            Your own name and problem, on a real order in that situation or on an order you invent.
          </p>
          <div className="mt-4 flex items-center gap-1 text-xs font-semibold text-brand">
            Start <ArrowRight size={13} className="transition-transform group-hover:translate-x-1" />
          </div>
        </Spotlight>
      </Link>
    </motion.div>
  );
}
