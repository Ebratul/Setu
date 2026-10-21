import Link from "next/link";
import type { MDXComponents } from "mdx/types";
import type { ComponentProps, ReactNode } from "react";

import { TierBadge } from "@/components/ui/TierBadge";
import type { DocLang } from "@/lib/docs/types";

import { Callout } from "./Callout";
import { FAQ, FAQItem } from "./FAQ";
import { Kbd } from "./Kbd";
import { RoleBadge } from "./RoleBadge";
import { Screenshot } from "./Screenshot";
import { Step, Steps } from "./Steps";
import { TryItButton } from "./TryItButton";
import { Video } from "./Video";

function Anchor({ href = "", children, ...rest }: ComponentProps<"a">) {
  if (href.startsWith("/")) {
    return (
      <Link href={href} {...(rest as object)}>
        {children}
      </Link>
    );
  }
  if (href.startsWith("#")) return <a href={href} {...rest}>{children}</a>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
      {children}
    </a>
  );
}

function Table({ children }: { children?: ReactNode }) {
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="table">
      <table>{children}</table>
    </div>
  );
}

/** Components every MDX page can use without importing. `lang` picks the screenshot folder. */
export function mdxComponents(lang: DocLang): MDXComponents {
  return {
    a: Anchor,
    table: Table,
    Steps,
    Step,
    Callout,
    RoleBadge,
    TierBadge,
    TryItButton,
    Kbd,
    FAQ,
    FAQItem,
    Video,
    Screenshot: (props: ComponentProps<typeof Screenshot>) => <Screenshot {...props} lang={lang} />,
  };
}
