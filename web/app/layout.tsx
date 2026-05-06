import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import { AppProviders } from '@/providers/app-providers'
import './globals.css'

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: 'Polaris Edge',
  description: 'Composite signals + regime state across the top-cap set',
  generator: 'v0.app',
  // AUDIT-2026-05-05 (P0-9): apple-mobile-web-app-* metas so iOS PWA /
  // Capacitor in-WebView modes render the app shell with the right
  // status-bar style instead of a transparent system bar over content.
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Polaris Edge',
  },
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

// AUDIT-2026-05-05 (P0-9, Tier 7 Capacitor compat): viewportFit:'cover'
// is required for iOS notch / Dynamic Island so safe-area-inset-* CSS
// vars resolve to non-zero. Without this the content area underflows
// the status bar and the home indicator on iPhone 12+ devices.
export const viewport: Viewport = {
  themeColor: '#0a0a0f',
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} bg-bg-0`} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <AppProviders>
          {children}
        </AppProviders>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
