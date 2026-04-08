/**
 * Footer — Auto-generated layout component
 * Generated: 2026-04-03
 *
 * Footer with links, copyright, and newsletter
 */

import React, { FC, ReactNode, useState } from 'react';
import { Mail, Send } from 'lucide-react';
import clsx from 'clsx';

export interface FooterLink {
  label: string;
  href: string;
}

export interface FooterColumn {
  title: string;
  links: FooterLink[];
}

export interface SocialLink {
  icon: ReactNode;
  url: string;
  label: string;
}

export interface FooterProps {
  columns?: FooterColumn[];
  copyright?: string;
  showNewsletter?: boolean;
  socials?: SocialLink[];
  onNewsletterSubscribe?: (email: string) => void;
  className?: string;
}

/**
 * Footer Component
 *
 * Features:
 * - Multi-column link layout
 * - Newsletter subscription form
 * - Social media links
 * - Copyright information
 * - Responsive (single column on mobile)
 * - Full accessibility (ARIA, semantic HTML)
 *
 * Accessibility:
 * - role="contentinfo"
 * - Semantic <footer> element
 * - Link context with aria-label
 * - Form semantics for newsletter
 */
export const Footer: FC<FooterProps> = ({
  columns = [],
  copyright = `© ${new Date().getFullYear()} Your Company. All rights reserved.`,
  showNewsletter = true,
  socials = [],
  onNewsletterSubscribe,
  className,
}) => {
  const [email, setEmail] = useState('');
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubscribe = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !email.includes('@')) {
      alert('Please enter a valid email');
      return;
    }

    setLoading(true);
    try {
      await onNewsletterSubscribe?.(email);
      setSubscribed(true);
      setEmail('');
      setTimeout(() => setSubscribed(false), 5000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <footer
      role="contentinfo"
      className={clsx('bg-dark-100 border-t border-gray-800 mt-auto', className)}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Main Footer Content */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 mb-12">
          {/* Link Columns */}
          {columns.map((column, idx) => (
            <div key={idx}>
              <h3 className="text-sm font-semibold text-white mb-4">{column.title}</h3>
              <ul className="space-y-2">
                {column.links.map((link, linkIdx) => (
                  <li key={linkIdx}>
                    <a
                      href={link.href}
                      className="text-sm text-gray-400 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-cyan-500 rounded px-2 py-1"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          {/* Newsletter Subscribe */}
          {showNewsletter && (
            <div>
              <h3 className="text-sm font-semibold text-white mb-4">Subscribe to our newsletter</h3>
              <form onSubmit={handleSubscribe} className="space-y-2">
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email"
                    className={clsx(
                      'flex-1 px-3 py-2 bg-dark-200 border border-gray-700 rounded',
                      'text-white placeholder-gray-500',
                      'focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent',
                      'transition-colors'
                    )}
                    disabled={loading}
                    aria-label="Email for newsletter"
                  />
                  <button
                    type="submit"
                    disabled={loading || !email}
                    className={clsx(
                      'px-3 py-2 rounded text-white transition-colors',
                      'focus:outline-none focus:ring-2 focus:ring-cyan-500',
                      loading || !email
                        ? 'bg-gray-700 cursor-not-allowed'
                        : 'bg-cyan-600 hover:bg-cyan-700'
                    )}
                    aria-label="Subscribe to newsletter"
                  >
                    {loading ? (
                      <span className="inline-block w-4 h-4 animate-spin">⟳</span>
                    ) : (
                      <Send size={16} />
                    )}
                  </button>
                </div>
                {subscribed && (
                  <p className="text-xs text-green-400">✓ Thanks for subscribing!</p>
                )}
              </form>
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="border-t border-gray-800 pt-8">
          <div className="flex flex-col-reverse md:flex-row items-center justify-between gap-4">
            {/* Copyright */}
            <p className="text-sm text-gray-400">{copyright}</p>

            {/* Social Links */}
            {socials.length > 0 && (
              <div className="flex items-center gap-4">
                {socials.map((social, idx) => (
                  <a
                    key={idx}
                    href={social.url}
                    aria-label={social.label}
                    className={clsx(
                      'text-gray-400 hover:text-white transition-colors',
                      'focus:outline-none focus:ring-2 focus:ring-cyan-500 rounded p-1'
                    )}
                  >
                    {social.icon}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
