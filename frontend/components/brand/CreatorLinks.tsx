"use client";

import { useEffect, useState } from "react";
import { api, type CreatorIdentity } from "@/lib/api";
import { cn } from "@/lib/utils";

const DEFAULT_GITHUB_USERNAME = "abhinavsinghparihar";

function safeGitHubUsername(value: string | undefined): string {
  return value && /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(value)
    ? value : DEFAULT_GITHUB_USERNAME;
}

function safeLinkedInUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && ["linkedin.com", "www.linkedin.com"].includes(url.hostname)
      && !url.username && !url.password && !url.search && !url.hash && url.pathname !== "/"
      ? url.toString() : null;
  } catch {
    return null;
  }
}

export function CreatorLinks({ className }: { className?: string }) {
  const [identity, setIdentity] = useState<CreatorIdentity | null>(null);

  useEffect(() => {
    let current = true;
    void api.creatorIdentity().then((result) => {
      if (current) setIdentity(result);
    }).catch(() => {
      // The canonical repository link remains available if the backend is down.
    });
    return () => { current = false; };
  }, []);

  const username = safeGitHubUsername(identity?.github_username);
  const linkedin = safeLinkedInUrl(identity?.linkedin_url);

  return (
    <nav aria-label="Creator profiles" className={cn("flex items-center justify-center gap-3", className)}>
      <a
        href={`https://github.com/${username}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-[10px] text-muted transition-colors hover:text-gold-bright"
        aria-label="Abhinav Singh on GitHub"
      >
        GitHub ↗
      </a>
      {linkedin && (
        <a
          href={linkedin}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-[10px] text-muted transition-colors hover:text-gold-bright"
          aria-label="Abhinav Singh on LinkedIn"
        >
          LinkedIn ↗
        </a>
      )}
    </nav>
  );
}
