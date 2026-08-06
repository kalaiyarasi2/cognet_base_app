import { createFileRoute, Redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/invoice")({
  component: InvoiceRedirect,
});

function InvoiceRedirect() {
  return <Redirect to="/drive-gpu" search={{ pipeline: "INVOICE" }} />;
}
