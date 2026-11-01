import { CareDialog } from "./CareDialog";
import type { LineRow } from "./types";

// Kept so existing imports keep working; the dialog itself is CareDialog.
// TODO: delete this file once the project lead agrees (nothing imports it any more).
export const SuspendDialog = ({ line, onClose }: { line: LineRow; onClose: () => void }) => <CareDialog kind="suspend" line={line} onClose={onClose} />;
