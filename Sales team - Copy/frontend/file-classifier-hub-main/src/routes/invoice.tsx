import { createFileRoute, Navigate } from "@tanstack/react-router";

export const Route = createFileRoute("/invoice")({
  component: InvoiceRedirect,
});

function InvoiceRedirect() {
  return <Navigate to="/drive-gpu" search={{ pipeline: "INVOICE" }} />;
}
