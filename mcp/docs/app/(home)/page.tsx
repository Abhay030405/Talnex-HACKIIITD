import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="tx-home">
      <p className="tx-home__kicker">TalNex · MCP server</p>
      <h1 className="tx-home__title">Proof of what actually works, from inside your AI assistant.</h1>
      <p className="tx-home__lead">
        Create a hackathon event, add teams, see what a check would cost, start it, watch the agent test each live site,
        and read the proof card, all by asking Claude or Gemini. Nothing that spends money starts until you confirm.
      </p>
      <div className="tx-home__actions">
        <Link href="/docs/quick-start" className="tx-button tx-button--primary">Quick start</Link>
        <Link href="/docs/connect" className="tx-button">Connect and test it yourself</Link>
        <Link href="/docs" className="tx-button">Read the docs</Link>
      </div>
    </main>
  );
}
