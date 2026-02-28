export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: 'system-ui', margin: 24, background: '#0f0f0f', color: '#e0e0e0' }}>
        <h1 style={{ marginBottom: 16 }}>PredExchange</h1>
        <p style={{ color: '#666', fontSize: 12, marginTop: -8, marginBottom: 16 }}>Run the API in another terminal: <code>predex api</code> or <code>predex api --with-ingestion</code> (API + live data in one process)</p>
        <nav style={{ marginBottom: 24 }}>
          <a href="/" style={{ marginRight: 16, color: '#7dd' }}>Home</a>
          <a href="/markets" style={{ marginRight: 16, color: '#7dd' }}>Markets</a>
          <a href="/compare" style={{ marginRight: 16, color: '#7dd' }}>Compare</a>
          <a href="/sports" style={{ marginRight: 16, color: '#7dd' }}>Sports</a>
          <a href="/sim" style={{ marginRight: 16, color: '#7dd' }}>Sim Runs</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
