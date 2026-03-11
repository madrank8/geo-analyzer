"""
SEER Scan Remediation Engine — Generates actionable fix instructions per classifier.

For each weak classifier, produces:
  - what:     Plain-English explanation of the problem
  - fix:      Step-by-step instructions to resolve
  - effort:   "quick" | "moderate" | "significant"
  - priority: "critical" | "high" | "medium" | "low"

Uses classifier definition + score + evidence to generate contextual guidance.
Falls back to category-level templates when no specific remediation exists.
"""

# ── Per-classifier remediation templates ──────────────────────────────
# Keys: classifier ID → dict with "what", "fix" (list of steps), "effort"
# Score-dependent: {fix} can reference {score} and {evidence} via .format()

REMEDIATION_MAP = {
    # ════ Identity & Entity Foundations ════
    "topical_authority": {
        "what": "Your site doesn't demonstrate deep expertise in a focused topic area. Google rewards sites that consistently cover one subject thoroughly.",
        "fix": [
            "Identify your 1-2 core topics and audit all pages — remove or noindex content that dilutes your focus",
            "Create a content hub: 1 pillar page + 8-12 supporting articles interlinked around your primary topic",
            "Ensure your domain name, title tags, and meta descriptions consistently reinforce your niche",
            "Add author bios with credentials specific to your topic area"
        ],
        "effort": "significant"
    },
    "knowledge_graph": {
        "what": "Your entity isn't well-connected in Google's Knowledge Graph. This limits how Google understands and trusts your brand.",
        "fix": [
            "Add Organization schema (schema.org) with sameAs links to your Wikipedia, Wikidata, LinkedIn, and social profiles",
            "Create or update your Wikidata entry with accurate structured data",
            "Ensure your Google Business Profile is claimed and fully completed",
            "Build citations on authoritative directories (BBB, industry associations, Crunchbase)"
        ],
        "effort": "moderate"
    },
    "brand_authority": {
        "what": "Your brand signals are weak — Google can't confidently identify your brand as a trusted entity.",
        "fix": [
            "Ensure consistent NAP (Name, Address, Phone) across all web properties",
            "Secure branded search results: claim Google Business Profile, social media handles, and directory listings",
            "Generate branded mentions through PR, guest posts, and industry partnerships",
            "Add Organization or LocalBusiness schema with logo, foundingDate, and description"
        ],
        "effort": "moderate"
    },
    "entity_coherence": {
        "what": "Your entity information is inconsistent across the web — different names, addresses, or descriptions confuse Google.",
        "fix": [
            "Audit all directory listings, social profiles, and citations for exact name/address/phone consistency",
            "Use the exact same business name everywhere (no abbreviations or variations)",
            "Update outdated listings that show old addresses or phone numbers",
            "Consolidate duplicate Google Business Profiles if any exist"
        ],
        "effort": "moderate"
    },
    "keyword_cannibalization": {
        "what": "Multiple pages on your site compete for the same keywords, splitting your ranking power.",
        "fix": [
            "Map each target keyword to exactly ONE page — create a keyword-to-URL spreadsheet",
            "Merge thin pages that target the same query into one comprehensive page",
            "Use canonical tags to point duplicate/similar pages to the primary version",
            "Differentiate page intent: make each page serve a distinct search intent (informational vs transactional)"
        ],
        "effort": "moderate"
    },
    "entity_association": {
        "what": "Your entity isn't strongly connected to the concepts, people, or organizations it should be associated with.",
        "fix": [
            "Mention related authoritative entities naturally in your content (industry bodies, certifications, partners)",
            "Add structured data with sameAs and memberOf properties",
            "Get featured on industry association websites and partner pages",
            "Create content that explicitly connects your entity to your niche's key concepts"
        ],
        "effort": "moderate"
    },
    "brand_voice_dilution": {
        "what": "Your content doesn't have a consistent, recognizable voice — it reads generic rather than distinctive.",
        "fix": [
            "Create a brand voice guide: define your tone (formal/casual), vocabulary, and writing personality",
            "Audit AI-generated content for generic phrasing and rewrite with your unique perspective",
            "Include first-person experience, opinions, and proprietary data that only your brand can provide",
            "Use consistent terminology across all pages"
        ],
        "effort": "moderate"
    },
    "entity_recognition_strength": {
        "what": "Google's NLP can't clearly identify your primary entity from your content.",
        "fix": [
            "Use your exact entity name in the title tag, H1, first paragraph, and meta description",
            "Add Organization/Person schema with comprehensive properties",
            "Ensure your entity name appears 3-5 times naturally in your main content",
            "Avoid using only pronouns or abbreviations — spell out your full entity name"
        ],
        "effort": "quick"
    },

    # ════ Local & Spatial Grounding ════
    "local_prominence": {
        "what": "Your local presence signals are weak. Google can't confidently rank you for location-based searches.",
        "fix": [
            "Fully complete your Google Business Profile: all categories, attributes, services, and business description",
            "Build citations on the top 50 local directories (Yelp, YP, Foursquare, Apple Maps, Bing Places)",
            "Generate genuine Google reviews — aim for 5+ new reviews per month with keyword-rich responses",
            "Add LocalBusiness schema with geo coordinates, service area, and opening hours"
        ],
        "effort": "significant"
    },
    "geographic_authority": {
        "what": "Your content doesn't establish geographic expertise for your service area.",
        "fix": [
            "Create location-specific landing pages for each city/area you serve",
            "Include local landmarks, neighborhood names, and region-specific content",
            "Add a detailed service area page with an embedded Google Map",
            "Get listed on local chamber of commerce and community organization websites"
        ],
        "effort": "moderate"
    },
    "neighborhood_granularity": {
        "what": "Your content doesn't reference specific neighborhoods, streets, or micro-locations.",
        "fix": [
            "Mention specific neighborhoods, districts, and landmarks in your content naturally",
            "Create neighborhood-specific pages or blog posts about local topics",
            "Include driving directions referencing local streets and intersections",
            "Add photos geotagged to your actual location"
        ],
        "effort": "quick"
    },
    "local_review_sentiment": {
        "what": "Your review sentiment is negative or mixed, which hurts local ranking signals.",
        "fix": [
            "Respond professionally to ALL negative reviews — acknowledge the issue and offer resolution",
            "Implement a review generation strategy: ask satisfied customers at the point of service",
            "Address recurring complaints by fixing the underlying service issue",
            "Don't buy or fake reviews — Google detects this and penalizes severely"
        ],
        "effort": "moderate"
    },

    # ════ Trust, Credentials & Legal ════
    "regulatory_compliance": {
        "what": "Your site is missing required legal/regulatory disclosures for your industry.",
        "fix": [
            "Add a Privacy Policy page (required for GDPR/CCPA) — link it in the footer of every page",
            "Add Terms of Service / Terms and Conditions page",
            "If applicable: add required industry disclaimers (financial, medical, legal advice disclaimers)",
            "Display any required licenses, certifications, or registration numbers prominently"
        ],
        "effort": "quick"
    },
    "technical_certifications": {
        "what": "Your certifications, licenses, or professional credentials aren't visible or verified on your site.",
        "fix": [
            "Add a dedicated 'Certifications' or 'Credentials' section on your About page",
            "Display certification logos/badges with links to verification pages",
            "Add hasCredential and qualifications to your Person/Organization schema",
            "Link to the issuing organization's website for each certification"
        ],
        "effort": "quick"
    },
    "missing_privacy_terms": {
        "what": "Your website is missing Privacy Policy and/or Terms of Service — a major trust and legal signal.",
        "fix": [
            "Add a Privacy Policy page covering data collection, cookies, and user rights (GDPR/CCPA compliant)",
            "Add a Terms of Service page defining usage rules and liability",
            "Link both pages from your site footer on every page",
            "If you collect emails/data: add cookie consent banner with opt-in"
        ],
        "effort": "quick"
    },

    # ════ Content Utility & Experience ════
    "helpful_content": {
        "what": "Your content may not satisfy Google's Helpful Content System — it reads as written for search engines rather than people.",
        "fix": [
            "Rewrite content to answer the specific question a searcher would have — be direct and useful",
            "Add first-hand experience: personal stories, proprietary data, original research, or real examples",
            "Remove thin sections that pad word count without adding value",
            "Ensure every page has a clear purpose and provides something competitors don't"
        ],
        "effort": "significant"
    },
    "eeat_experience": {
        "what": "Your content lacks demonstrable first-hand experience with the topic.",
        "fix": [
            "Add personal anecdotes, case studies, or 'I tested this' narratives",
            "Include original photos/videos of you using or doing what you write about",
            "Reference specific dates, places, and details that prove real experience",
            "Add author bylines with bios that demonstrate relevant experience"
        ],
        "effort": "moderate"
    },
    "information_gain": {
        "what": "Your content doesn't add new information beyond what's already available in search results.",
        "fix": [
            "Conduct original research, surveys, or data analysis and publish the findings",
            "Include proprietary data, internal metrics, or unique case studies",
            "Provide expert opinions or contrarian takes that competitors don't cover",
            "Add step-by-step tutorials based on your actual process, not just rewritten guides"
        ],
        "effort": "significant"
    },
    "content_freshness_alignment": {
        "what": "Your content appears outdated — dates, statistics, and references are stale.",
        "fix": [
            "Update all statistics and data to the current year",
            "Add a 'Last Updated' date visible on the page and in schema markup",
            "Review and update all external links — remove broken ones, replace with current sources",
            "Add a section addressing recent developments or changes in your topic area"
        ],
        "effort": "quick"
    },

    # ════ Linguistic Authenticity & AI Detection ════
    "lexical_diversity": {
        "what": "Your vocabulary is repetitive — the same words and phrases appear too often, signaling AI-generated or low-effort content.",
        "fix": [
            "Use a thesaurus to vary your vocabulary — avoid repeating the same descriptors",
            "Break up predictable sentence patterns: mix short punchy sentences with longer complex ones",
            "Replace generic filler words (very, really, just, actually) with specific, vivid language",
            "Read your content aloud — if it sounds monotonous, rewrite those sections"
        ],
        "effort": "moderate"
    },
    "syntactic_burstiness": {
        "what": "Your sentences are all similar in length and structure — a strong AI-content fingerprint.",
        "fix": [
            "Deliberately vary sentence length: follow a long sentence with a short punchy one. Then medium.",
            "Mix sentence types: declarative, interrogative, imperative, and exclamatory",
            "Add parenthetical asides, em-dashes, and sentence fragments for natural rhythm",
            "Read competitor content that ranks well and note their sentence length variation"
        ],
        "effort": "moderate"
    },
    "cliche_density": {
        "what": "Your content is packed with clichés and overused phrases that signal low-quality or AI-generated text.",
        "fix": [
            "Search for and replace: 'cutting-edge', 'game-changer', 'leverage', 'delve', 'landscape', 'robust', 'seamlessly'",
            "Replace abstract phrases with specific concrete examples",
            "Remove corporate jargon: 'synergy', 'paradigm shift', 'best-in-class', 'holistic approach'",
            "Use plain, direct language instead — 'use' not 'leverage', 'help' not 'empower'"
        ],
        "effort": "quick"
    },
    "passive_voice_saturation": {
        "what": "Too much passive voice makes your content feel academic and impersonal.",
        "fix": [
            "Identify passive constructions (was done, is performed, has been shown) and rewrite in active voice",
            "Name the actor: instead of 'The report was written', say 'Sarah wrote the report'",
            "Aim for less than 10% passive voice across your content",
            "Use tools like Hemingway Editor to highlight passive constructions"
        ],
        "effort": "quick"
    },
    "prompt_leakage": {
        "what": "Your content contains phrases that suggest AI prompt instructions leaked into the output.",
        "fix": [
            "Search for telltale phrases: 'As an AI', 'I cannot', 'As a language model', 'Here is', 'In conclusion'",
            "Remove any meta-instructions that slipped through: 'Write a...', 'Create a...', 'Generate...'",
            "Check for unnatural formatting cues like 'Section 1:', 'Key Takeaway:', 'Important Note:'",
            "Have a human editor review all AI-assisted content before publishing"
        ],
        "effort": "quick"
    },

    # ════ Visual Intelligence & Realism ════
    "human_presence": {
        "what": "Your site lacks real photos of actual people — team members, customers, or the business owner.",
        "fix": [
            "Add genuine team photos on your About page — not stock photos",
            "Include photos of real customers or your team at work (with permission)",
            "Add headshots to author bylines and team member bios",
            "Use EXIF-preserved, original photos rather than heavily edited stock imagery"
        ],
        "effort": "moderate"
    },
    "image_alt_optimization": {
        "what": "Your images are missing alt text or have generic/empty alt attributes.",
        "fix": [
            "Add descriptive alt text to every image — describe what's shown, not just 'image' or 'photo'",
            "Include your target keyword naturally in 1-2 image alt texts per page",
            "Don't keyword stuff alt text — write for accessibility first, SEO second",
            "For decorative images, use alt='' (empty) to signal they're non-content"
        ],
        "effort": "quick"
    },

    # ════ Technical Infrastructure & Logic ════
    "schema_structured_data": {
        "what": "Your site is missing or has incomplete structured data (schema.org markup).",
        "fix": [
            "Add Organization or LocalBusiness schema on your homepage with name, url, logo, contactPoint",
            "Add Article/BlogPosting schema to content pages with author, datePublished, dateModified",
            "Add BreadcrumbList schema for navigation hierarchy",
            "Validate your schema at https://validator.schema.org/ and fix all errors"
        ],
        "effort": "moderate"
    },
    "schema_grounding_depth": {
        "what": "Your schema markup is too shallow — it exists but lacks the detail Google needs for rich results.",
        "fix": [
            "Expand your schema with sameAs, hasCredential, areaServed, and knowsAbout properties",
            "Add FAQ schema for pages with question-answer content",
            "Add Review/AggregateRating schema if you have testimonials",
            "Nest schema properly: Organization > employee > Person > hasCredential"
        ],
        "effort": "moderate"
    },
    "sge_compatibility": {
        "what": "Your content structure isn't optimized for Google's AI Overview / SGE features.",
        "fix": [
            "Structure content with clear Q&A format — use headers as questions, paragraphs as direct answers",
            "Add concise summary paragraphs (2-3 sentences) at the top of each section",
            "Use structured lists for how-to steps, features, and comparisons",
            "Include FAQ sections that directly answer common questions about your topic"
        ],
        "effort": "moderate"
    },
    "core_web_vitals": {
        "what": "Your site likely has poor Core Web Vitals (loading speed, interactivity, visual stability).",
        "fix": [
            "Run PageSpeed Insights (pagespeed.web.dev) and address every red/orange issue",
            "Optimize images: compress, use WebP format, add width/height attributes, lazy-load below-fold images",
            "Minimize render-blocking CSS/JS: inline critical CSS, defer non-essential scripts",
            "Use a CDN and enable browser caching for static assets"
        ],
        "effort": "significant"
    },
    "mobile_optimization": {
        "what": "Your site has mobile usability issues — critical since Google uses mobile-first indexing.",
        "fix": [
            "Ensure your site is fully responsive — test on multiple phone sizes",
            "Make tap targets at least 48x48px with adequate spacing between them",
            "Ensure text is readable without zooming (minimum 16px body font)",
            "Fix any horizontal scrolling issues — no content should overflow the viewport"
        ],
        "effort": "moderate"
    },

    # ════ External Signals & Market Reputation ════
    "review_sentiment_trust": {
        "what": "Your online reviews show mixed or negative sentiment, hurting trust signals.",
        "fix": [
            "Respond to every review (positive and negative) within 24-48 hours",
            "For negative reviews: acknowledge, apologize, offer to resolve offline",
            "Implement a systematic review request process after positive customer interactions",
            "Address systemic issues mentioned in reviews — Google watches for pattern improvements"
        ],
        "effort": "moderate"
    },
    "user_interaction_signals": {
        "what": "Behavioral signals suggest users aren't engaging well with your site (low dwell time, high bounce).",
        "fix": [
            "Improve your above-the-fold content — answer the user's query immediately, don't bury it",
            "Add engaging elements: videos, interactive tools, expandable sections",
            "Improve internal linking to keep users navigating your site",
            "Reduce friction: faster load times, no intrusive interstitials, clear navigation"
        ],
        "effort": "moderate"
    },

    # ════ Link Profile & Off-Page Authority ════
    "link_value": {
        "what": "Your site lacks quality backlinks from authoritative, relevant sources.",
        "fix": [
            "Create linkable assets: original research, free tools, comprehensive guides, infographics",
            "Pursue relevant guest posting opportunities on industry blogs (avoid spam networks)",
            "Get listed on relevant industry directories and resource pages",
            "Build relationships with journalists and bloggers who cover your niche (HARO, Qwoted)"
        ],
        "effort": "significant"
    },
    "link_toxicity": {
        "what": "Your link profile contains low-quality or spammy backlinks that may trigger penalties.",
        "fix": [
            "Audit your backlinks using Google Search Console or Ahrefs",
            "Identify and disavow toxic links: PBNs, link farms, irrelevant foreign sites, paid link schemes",
            "Submit a disavow file through Google Search Console",
            "Stop any active link-building that uses low-quality or purchased links"
        ],
        "effort": "moderate"
    },

    # ════ Integrity Risk & Anti-Abuse ════
    "scaled_content": {
        "what": "Your site shows signs of mass-produced content — Google's Scaled Content System may flag this.",
        "fix": [
            "Audit all pages: remove or consolidate any that were bulk-generated without editorial oversight",
            "Add unique value to each page: proprietary data, expert quotes, original analysis",
            "Ensure every page has a distinct purpose — no near-duplicate pages targeting keyword variants",
            "Add author bylines with real, verifiable people to every content page"
        ],
        "effort": "significant"
    },
    "fake_expert_personas": {
        "what": "Your author profiles appear fabricated — stock photos, generic bios, or unverifiable credentials.",
        "fix": [
            "Use real team member photos and genuine professional biographies",
            "Link author profiles to verifiable external sources (LinkedIn, professional registrations)",
            "Add Person schema with sameAs links to real social/professional profiles",
            "If using freelancers: have them write under their real name with real credentials"
        ],
        "effort": "quick"
    },

    # ════ Behavioral Validation & User Interaction ════
    "intent_capture_speed": {
        "what": "Users can't find what they need quickly — your content doesn't match search intent efficiently.",
        "fix": [
            "Put the direct answer to the page's target query in the first 2 sentences",
            "Use a table of contents for long pages so users can jump to their section",
            "Match the content format to the intent: listicle for 'best X', tutorial for 'how to X', comparison for 'X vs Y'",
            "Remove introductory fluff — don't make users scroll to find the value"
        ],
        "effort": "quick"
    },
    "action_visibility": {
        "what": "Your calls-to-action are buried or unclear — users don't know what to do next.",
        "fix": [
            "Place your primary CTA above the fold and repeat it after key content sections",
            "Use clear, specific button text: 'Get Free Quote' not 'Submit', 'Book Appointment' not 'Click Here'",
            "Ensure CTAs visually stand out with contrasting colors and adequate size",
            "Add contextual CTAs that relate to the content section they're in"
        ],
        "effort": "quick"
    },

    # ════ Temporal Dynamics & Stability ════
    "query_deserves_freshness": {
        "what": "Your content doesn't reflect current information for a query that requires freshness.",
        "fix": [
            "Update the page with current-year statistics, prices, and developments",
            "Add a 'Last Updated' date to the page and update it with each revision",
            "Set a content review schedule: monthly for fast-moving topics, quarterly for evergreen",
            "Add dateModified to your Article schema to signal freshness to Google"
        ],
        "effort": "quick"
    },
    "update_velocity": {
        "what": "Your site is updated too infrequently — stale sites lose freshness signals over time.",
        "fix": [
            "Establish a minimum publishing cadence: at least 2-4 pieces per month",
            "Regularly update your top-performing pages with new data and insights",
            "Add a blog or news section for timely content related to your niche",
            "Update your sitemap lastmod dates when you genuinely modify content"
        ],
        "effort": "moderate"
    },
}


# ── Category-level fallback remediation ───────────────────────────────
# Used when a specific classifier doesn't have its own entry above
CATEGORY_REMEDIATION = {
    "Identity & Entity Foundations": {
        "what": "Your brand's entity identity is not well-established in Google's understanding.",
        "fix": [
            "Strengthen your Organization/Person schema markup with comprehensive properties",
            "Ensure consistent entity naming across all web properties and citations",
            "Build authoritative mentions and references from trusted industry sources",
            "Create content that reinforces your core expertise and entity associations"
        ],
        "effort": "moderate"
    },
    "Local & Spatial Grounding": {
        "what": "Your local presence signals need strengthening for location-based search visibility.",
        "fix": [
            "Complete and optimize your Google Business Profile with all available attributes",
            "Build consistent citations across local directories and platforms",
            "Create location-specific content referencing real neighborhoods and landmarks",
            "Generate authentic reviews and respond to all feedback promptly"
        ],
        "effort": "moderate"
    },
    "Trust, Credentials & Legal": {
        "what": "Your site is missing trust signals — legal pages, credentials, or verified expertise markers.",
        "fix": [
            "Add Privacy Policy, Terms of Service, and any required industry disclaimers",
            "Display certifications, licenses, and credentials with verification links",
            "Add trust badges, secure checkout indicators, and contact information prominently",
            "Ensure HTTPS is active and properly configured across all pages"
        ],
        "effort": "quick"
    },
    "Content Utility & Experience": {
        "what": "Your content isn't providing enough unique value to satisfy Google's quality standards.",
        "fix": [
            "Rewrite content to directly answer searcher questions with first-hand experience",
            "Add original data, proprietary insights, or real case studies",
            "Ensure every page has a clear purpose beyond ranking for keywords",
            "Improve readability: clear structure, scannable format, helpful media"
        ],
        "effort": "significant"
    },
    "Linguistic Authenticity & AI Detection": {
        "what": "Your content shows patterns typical of AI-generated text — repetitive structure, generic phrasing.",
        "fix": [
            "Vary sentence length and structure — break predictable patterns",
            "Replace AI-signature words (delve, leverage, landscape, robust, seamlessly)",
            "Add personal voice, opinions, and specific real-world details",
            "Have a human editor review and rewrite AI-assisted sections"
        ],
        "effort": "moderate"
    },
    "Visual Intelligence & Realism": {
        "what": "Your visual content is weak — missing, generic, or inconsistent with your brand.",
        "fix": [
            "Add original, high-quality photos of real people, products, and locations",
            "Optimize all images with descriptive alt text and proper sizing",
            "Remove obvious stock photos and replace with authentic imagery",
            "Add team photos, process images, and behind-the-scenes content"
        ],
        "effort": "moderate"
    },
    "External Signals & Market Reputation": {
        "what": "Your off-site reputation signals (reviews, mentions, social proof) need improvement.",
        "fix": [
            "Implement a systematic review generation and response strategy",
            "Build brand mentions through PR, guest content, and industry participation",
            "Monitor and respond to all online feedback within 24-48 hours",
            "Create shareable content that naturally generates social engagement"
        ],
        "effort": "moderate"
    },
    "Link Profile & Off-Page Authority": {
        "what": "Your link profile lacks quality — either too few authoritative links or too many low-quality ones.",
        "fix": [
            "Create linkable assets: original research, free tools, comprehensive guides",
            "Build relationships with industry publishers for natural link acquisition",
            "Audit existing backlinks and disavow toxic/spammy links",
            "Focus on relevance over volume — one link from an authority beats 100 from spam"
        ],
        "effort": "significant"
    },
    "Technical Infrastructure & Logic": {
        "what": "Your site has technical issues that impact Google's ability to crawl, index, and render properly.",
        "fix": [
            "Run Google PageSpeed Insights and address all critical issues",
            "Add comprehensive structured data (schema.org) and validate it",
            "Ensure proper canonical tags, XML sitemap, and robots.txt configuration",
            "Fix Core Web Vitals: LCP, FID/INP, and CLS"
        ],
        "effort": "moderate"
    },
    "Integrity Risk & Anti-Abuse": {
        "what": "Your site shows signals that may trigger Google's anti-abuse or spam systems.",
        "fix": [
            "Audit all content for signs of mass production, scraping, or thin quality",
            "Ensure all author profiles are real, verifiable people",
            "Remove any hidden text, keyword stuffing, or doorway pages",
            "Add genuine editorial value to every page — if you can't, consider removing it"
        ],
        "effort": "moderate"
    },
    "Behavioral Validation & User Interaction": {
        "what": "Users aren't engaging well with your content — signals suggest poor experience.",
        "fix": [
            "Put your key value proposition above the fold — answer the query immediately",
            "Improve page load speed and remove intrusive interstitials",
            "Add clear CTAs and logical content flow to guide user journeys",
            "Test your pages on mobile — ensure touch targets and readability are solid"
        ],
        "effort": "moderate"
    },
    "Temporal Dynamics & Stability": {
        "what": "Your content freshness signals are weak — Google may perceive your site as stale.",
        "fix": [
            "Update high-value pages with current data, statistics, and references",
            "Add dateModified to your Article/WebPage schema when updating content",
            "Maintain a regular publishing schedule for new content",
            "Review and refresh your top pages at least quarterly"
        ],
        "effort": "quick"
    },
}

# ── Priority calculation ──────────────────────────────────────────────
def get_priority(score: int, confidence: int) -> str:
    """Determine fix priority based on score and confidence."""
    if score < 20 and confidence >= 70:
        return "critical"
    if score < 30 and confidence >= 50:
        return "critical"
    if score < 40:
        return "high"
    if score < 50:
        return "high"
    if score < 60:
        return "medium"
    return "low"


def get_remediation(classifier_id: str, classifier_name: str, category: str,
                    score: int, evidence: str, confidence: int = 50,
                    definition: str = "") -> dict:
    """
    Get remediation data for a classifier.
    Returns dict with: what, fix (list), effort, priority
    """
    priority = get_priority(score, confidence)

    # Try specific remediation first
    if classifier_id in REMEDIATION_MAP:
        r = REMEDIATION_MAP[classifier_id]
        return {
            "what": r["what"],
            "fix": r["fix"],
            "effort": r.get("effort", "moderate"),
            "priority": priority,
        }

    # Fall back to category-level remediation
    if category in CATEGORY_REMEDIATION:
        r = CATEGORY_REMEDIATION[category]
        return {
            "what": r["what"],
            "fix": r["fix"],
            "effort": r.get("effort", "moderate"),
            "priority": priority,
        }

    # Generic fallback
    return {
        "what": f"The '{classifier_name}' signal scored low, indicating room for improvement.",
        "fix": [
            f"Review the evidence: \"{evidence}\"",
            "Research best practices for this specific SEO signal",
            "Implement changes and re-scan to measure improvement"
        ],
        "effort": "moderate",
        "priority": priority,
    }
