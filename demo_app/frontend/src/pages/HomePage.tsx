import { Link } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { useSession } from "../session/SessionProvider";

const TASKS = [
  { to: "/write", title: "Write a note", text: "A few minutes of free writing on a short prompt." },
  { to: "/form", title: "Fill in a form", text: "Name, address and a few choices, as on any contact form." },
  { to: "/payees", title: "Add a payee", text: "A high-risk action. You may be asked to confirm it is you." },
  { to: "/reports", title: "Export reports", text: "A high-risk action. You may be asked to confirm it is you." },
];

export function HomePage() {
  const { session } = useSession();
  const name = session.status === "signed_in" ? session.username : "";
  return (
    <div className="max-w-3xl">
      <PageHeader title={`Welcome, ${name}`}>
        <p>Use the app as you normally would. Each task below gives AuthWho ordinary typing and pointer activity.</p>
      </PageHeader>
      <ul className="grid grid-cols-2 gap-4">
        {TASKS.map((task) => (
          <li key={task.to}>
            <Link
              to={task.to}
              className="block h-full rounded-lg border border-line bg-paper p-5 hover:border-accent"
            >
              <span className="block text-base font-semibold text-accent">{task.title}</span>
              <span className="mt-1 block text-sm text-muted">{task.text}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
