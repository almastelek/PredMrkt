export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: 'system-ui', margin: 24, background: '#0f0f0f', color: '#e0e0e0' }}>
        <h1 style={{ marginBottom: 16 }}>PredExchange</h1>
        <nav style={{ marginBottom: 24 }}>
          <a href="/" style={{ marginRight: 16, color: '#7dd' }}>Home</a>
          <a href="/markets" style={{ marginRight: 16, color: '#7dd' }}>Markets</a>
          <a href="/sim" style={{ marginRight: 16, color: '#7dd' }}>Sim Runs</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
