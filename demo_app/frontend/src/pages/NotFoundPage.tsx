import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  return (
    <div className="max-w-2xl">
      <PageHeader title="Page not found">
        <p>There is no page at this address. Check the address, or start again from the home page.</p>
      </PageHeader>
      <Link to="/" className="font-medium text-accent underline">
        Go to the home page
      </Link>
    </div>
  );
}
