import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { RootProvider } from "fumadocs-ui/provider/next";

import SearchDialog from "@/components/docs/search";
import { baseOptions } from "@/lib/docs/layout.shared";
import { source } from "@/lib/docs/source";

// Vendor styles for this section only (fumadocs and React Flow); our colours, type and spacing come from globals.css.
import "./docs.css";

/** The docs, inside the website: system design, the MCP server and the API reference with its playground. */
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <RootProvider search={{ SearchDialog }} theme={{ enabled: false }}>
      <div className="docs-section">
        <DocsLayout tree={source.getPageTree()} {...baseOptions()}>
          {children}
        </DocsLayout>
      </div>
    </RootProvider>
  );
}
