# Design Systems Reference

A curated collection of real-world design systems for research-backed frontend decisions.
Use this reference when you need concrete examples, component precedents, or authoritative guidance
before designing or building UI, but do not need a full Refero screen/flow research pass yet.

## How to Use This Reference

1. Identify the product type and audience
2. Pick 2-3 design systems from the matching category
3. Visit their documentation for specific component patterns, typography scales, or color systems
4. Synthesize findings into your design instead of copying blindly

## Enterprise / B2B SaaS

Heavy on data density, accessibility, and consistent component behavior.

| Design System | Why Reference It | Best For |
|---------------|------------------|----------|
| [IBM Carbon](https://www.carbondesignsystem.com/) | Deep accessibility guidance, data visualization, enterprise patterns | Data-heavy dashboards, admin tools |
| [GitHub Primer](https://primer.style/) | Clean, developer-friendly UI, excellent component docs | Developer tools, Git-based products |
| [GitLab Pajamas](https://design.gitlab.com/) | Collaboration-focused patterns, clear voice and tone | Team collaboration, DevOps tools |
| [Atlassian Design System](https://atlassian.design) | Mature patterns for project management and teamwork | Jira/Trello-like productivity apps |
| [Salesforce Lightning](https://www.lightningdesignsystem.com) | Comprehensive enterprise CRM patterns | CRM, sales tools, complex workflows |
| [Shopify Polaris](https://polaris.shopify.com) | Merchant-focused UX, strong content guidelines | E-commerce admin, seller dashboards |
| [Twilio Paste](https://paste.twilio.design/) | Communication-focused, strong accessibility | Messaging, communication APIs |
| [Workday Canvas](https://design.workday.com/) | HR/Finance enterprise patterns, inclusive design | HR systems, finance tools |
| [HashiCorp Helios](https://helios.hashicorp.design) | Developer-centric, clean aesthetics | Infrastructure/DevOps products |
| [Elastic UI (EUI)](https://elastic.github.io/eui/) | Search and analytics heavy interfaces | Search, logging, observability tools |

## Open Source Component Libraries

Ready-to-use components with strong documentation. Good for implementation speed.

| Design System | Stack / Style | Why Reference It |
|---------------|---------------|------------------|
| [Ant Design](https://ant.design) | React, enterprise | Comprehensive B2B component set, strong table/form patterns |
| [Material Design](https://m3.material.io/) | Any platform | Definitive motion, elevation and mobile patterns |
| [Fluent UI](https://developer.microsoft.com/en-us/fluentui) | React, cross-platform | Productivity and Microsoft-style workflows |
| [Chakra UI](https://chakra-ui.com/) | React, modern | Accessibility-first and composable |
| [Mantine](https://mantine.dev/) | React, modern | Rich component set and docs |
| [Radix UI](https://www.radix-ui.com/) | Headless React | Accessibility-first primitives |
| [shadcn/ui](https://ui.shadcn.com/) | Tailwind + Radix | Copy-paste components with strong customization |
| [Blueprint](https://blueprintjs.com/) | React, desktop-like | Dense data interfaces for power users |

## Government / Public Service

Gold standards for accessibility, clarity, and inclusive design.

| Design System | Region | Why Reference It |
|---------------|--------|------------------|
| [GOV.UK Design System](https://design-system.service.gov.uk/) | UK | Plain language and ruthless clarity |
| [U.S. Web Design System](https://designsystem.digital.gov/) | USA | Federal accessibility requirements |
| [NHS.UK Service Manual](https://service-manual.nhs.uk/) | UK Health | Healthcare UX and anxiety reduction |
| [BBC GEL](https://www.bbc.co.uk/gel) | UK Media | Content-heavy, multi-platform UX |

## Consumer / Content / Media

Stronger brand expression, editorial layouts, and engagement patterns.

| Design System | Company | Why Reference It |
|---------------|---------|------------------|
| [Adobe Spectrum](https://spectrum.adobe.com) | Adobe | Creative tools, cross-platform consistency |
| [Apple HIG](https://developer.apple.com/design/) | Apple | Native patterns, motion, and spatial design |
| [Vercel Geist](https://vercel.com/geist) | Vercel | Minimal developer aesthetic and typography |
| [Pinterest Gestalt](https://pinterest.github.io/gestalt/) | Pinterest | Image-first layouts and content density |
| [Financial Times Origami](https://origami.ft.com/) | FT | Editorial hierarchy and typography |

## Specialized / Niche

| Design System | Domain | Why Reference It |
|---------------|--------|------------------|
| [PatternFly](https://www.patternfly.org/) | OpenShift / Kubernetes | Container and orchestration UIs |
| [Cloudscape](https://cloudscape.design/) | AWS | Dense table and console patterns |
| [Siemens iX](https://ix.siemens.io/) | Industrial / IoT | SCADA-like and industrial dashboards |
| [Porsche Design System](https://designsystem.porsche.com) | Automotive | Premium brand expression and motion |

## Quick Decision Guide

Use this flow to pick where to look first:

```text
Building a B2B/SaaS dashboard?
  -> IBM Carbon, GitHub Primer, Atlassian

Need a ready-to-use React component library?
  -> shadcn/ui, Chakra UI, Mantine, Ant Design

Working on government or healthcare services?
  -> GOV.UK, NHS, USWDS

Need strong visual/brand identity?
  -> Adobe Spectrum, Apple HIG, Vercel Geist

Designing for developers / technical users?
  -> GitHub Primer, HashiCorp Helios, Elastic UI
```

## Usage Rules

- Always cite the specific design system when recommending a pattern
- Prefer open-source systems when the user needs code examples
- Prefer government systems when the user needs accessibility or clarity guidance
- Prefer enterprise systems when the user needs complex data or workflow patterns
- Do not treat any design system as a mandate; use them as informed references

This reference was migrated from the old `design-systems-reference` standalone skill.
