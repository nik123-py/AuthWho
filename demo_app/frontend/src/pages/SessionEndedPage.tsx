import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";

export function SessionEndedPage() {
  return (
    <div className="max-w-2xl">
      <PageHeader title="Your session has ended">
        <p>
          For your security, this session was ended because the identity check did not succeed. Your account is
          not locked: sign in again to continue.
        </p>
      </PageHeader>
      <Link to="/login" className="font-medium text-accent underline">
        Sign in again
      </Link>
    </div>
  );
}
