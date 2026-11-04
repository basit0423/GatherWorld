import os,re,secrets,hashlib,smtplib,ssl,json,time
from decimal import Decimal, InvalidOperation
import urllib.request,urllib.error,urllib.parse
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from flask import Flask,render_template,request,redirect,url_for,session,flash,jsonify,abort
from dotenv import load_dotenv
import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash,check_password_hash
load_dotenv()
app=Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev-only-change-me"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0").strip() == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=34*1024*1024,  # 32 MB video allowance plus multipart overhead
)
ADMIN_USERNAMES={x.strip().lower() for x in os.getenv("ADMIN_USERNAMES", "").split(",") if x.strip()}
ADMIN_EMAILS={x.strip().lower() for x in os.getenv("ADMIN_EMAILS", "").split(",") if x.strip()}
MAIL_SERVER=os.getenv("MAIL_SERVER","").strip()
MAIL_PORT=int(os.getenv("MAIL_PORT","587"))
MAIL_USE_TLS=os.getenv("MAIL_USE_TLS","1").strip().lower() in ("1","true","yes","on")
MAIL_USERNAME=os.getenv("MAIL_USERNAME","").strip()
MAIL_PASSWORD=os.getenv("MAIL_PASSWORD","")
MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER",MAIL_USERNAME).strip()
DATABASE_URL=os.getenv("DATABASE_URL","").strip()
CLOUDINARY_CLOUD_NAME=os.getenv("CLOUDINARY_CLOUD_NAME","").strip()
CLOUDINARY_API_KEY=os.getenv("CLOUDINARY_API_KEY","").strip()
CLOUDINARY_API_SECRET=os.getenv("CLOUDINARY_API_SECRET","").strip()
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY","").strip()
GEMINI_MODEL=os.getenv("GEMINI_MODEL","gemini-3.8-flash").strip() or "gemini-3.8-flash"
try:
    GEMINI_TIMEOUT_SECONDS = max(20, min(int(os.getenv("GEMINI_TIMEOUT_SECONDS", "90")), 120))
except (TypeError, ValueError):
    GEMINI_TIMEOUT_SECONDS = 90
AVATAR_PRESETS = (
    "avatar_anime_blue.png", "avatar_anime_style.png", "avatar_cat_glasses.png",
    "avatar_futuristic_hood.png", "avatar_hijab_portrait.png", "avatar_hooded_person.png",
    "avatar_man_beard.png", "avatar_man_cap.png", "avatar_man_casual.png",
    "avatar_man_sunglasses.png", "avatar_neon_hood.png", "avatar_neon_portrait.png",
    "avatar_sunset_silhouette.png", "avatar_winter_hat.png", "avatar_woman_hat.png",
    "avatar_woman_profile.png", "avatar_woman_warm.png",
)
def db():
    if not DATABASE_URL: raise RuntimeError("DATABASE_URL missing in .env")
    return psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=10)
def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS gw_users(id BIGSERIAL PRIMARY KEY,username VARCHAR(30) UNIQUE NOT NULL,email VARCHAR(255) UNIQUE NOT NULL,password_hash TEXT NOT NULL,display_name VARCHAR(60) NOT NULL,bio VARCHAR(300) NOT NULL DEFAULT '',avatar_url TEXT,avatar_preset VARCHAR(120) NOT NULL DEFAULT 'avatar_anime_blue.png',created_at TIMESTAMPTZ DEFAULT NOW())""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_posts(id BIGSERIAL PRIMARY KEY,user_id BIGINT REFERENCES gw_users(id) ON DELETE CASCADE,body VARCHAR(2000) NOT NULL DEFAULT '',media_url TEXT,media_type VARCHAR(10),created_at TIMESTAMPTZ DEFAULT NOW(),CHECK(length(body)>0 OR media_url IS NOT NULL))""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_follows(follower_id BIGINT REFERENCES gw_users(id) ON DELETE CASCADE,followed_id BIGINT REFERENCES gw_users(id) ON DELETE CASCADE,created_at TIMESTAMPTZ DEFAULT NOW(),PRIMARY KEY(follower_id,followed_id),CHECK(follower_id<>followed_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_likes(user_id BIGINT REFERENCES gw_users(id) ON DELETE CASCADE,post_id BIGINT REFERENCES gw_posts(id) ON DELETE CASCADE,created_at TIMESTAMPTZ DEFAULT NOW(),PRIMARY KEY(user_id,post_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_comments(id BIGSERIAL PRIMARY KEY,post_id BIGINT REFERENCES gw_posts(id) ON DELETE CASCADE,user_id BIGINT REFERENCES gw_users(id) ON DELETE CASCADE,body VARCHAR(1000) NOT NULL,created_at TIMESTAMPTZ DEFAULT NOW())""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_posts_created_idx ON gw_posts(created_at DESC)")
        # Existing accounts remain verified; only newly registered accounts need OTP confirmation.
        c.execute("ALTER TABLE gw_users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT TRUE")
        c.execute("ALTER TABLE gw_users ADD COLUMN IF NOT EXISTS avatar_url TEXT")
        c.execute("ALTER TABLE gw_users ADD COLUMN IF NOT EXISTS avatar_preset VARCHAR(120) NOT NULL DEFAULT 'avatar_anime_blue.png'")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_email_otps(
            user_id BIGINT PRIMARY KEY REFERENCES gw_users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_password_resets(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            token_hash CHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_password_resets_user_idx ON gw_password_resets(user_id)")
        c.execute("ALTER TABLE gw_users ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("ALTER TABLE gw_users ADD COLUMN IF NOT EXISTS suspended_reason VARCHAR(500)")
        c.execute("ALTER TABLE gw_users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_rate_limits(
            bucket_key CHAR(64) PRIMARY KEY,
            window_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            hits INTEGER NOT NULL DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_user_blocks(
            blocker_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            blocked_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(blocker_id, blocked_id), CHECK(blocker_id <> blocked_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_reports(
            id BIGSERIAL PRIMARY KEY,
            reporter_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            content_type VARCHAR(12) NOT NULL CHECK(content_type IN ('post','user')),
            content_id BIGINT NOT NULL,
            reason VARCHAR(40) NOT NULL,
            details VARCHAR(1000) NOT NULL DEFAULT '',
            status VARCHAR(12) NOT NULL DEFAULT 'open' CHECK(status IN ('open','dismissed','actioned')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ,
            resolved_by BIGINT REFERENCES gw_users(id) ON DELETE SET NULL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_reports_status_idx ON gw_reports(status, created_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_admin_actions(
            id BIGSERIAL PRIMARY KEY,
            admin_id BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            action VARCHAR(40) NOT NULL,
            target_type VARCHAR(12) NOT NULL,
            target_id BIGINT,
            note VARCHAR(500) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        # Phase 3: saved posts, reposts, notifications and threaded comment replies.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_bookmarks(
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            post_id BIGINT NOT NULL REFERENCES gw_posts(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, post_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_bookmarks_user_idx ON gw_bookmarks(user_id, created_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_reposts(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            post_id BIGINT NOT NULL REFERENCES gw_posts(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, post_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_reposts_created_idx ON gw_reposts(created_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_notifications(
            id BIGSERIAL PRIMARY KEY,
            recipient_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            actor_id BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            notification_type VARCHAR(24) NOT NULL,
            entity_type VARCHAR(16),
            entity_id BIGINT,
            message VARCHAR(240) NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_notifications_recipient_idx ON gw_notifications(recipient_id, is_read, created_at DESC)")
        c.execute("ALTER TABLE gw_comments ADD COLUMN IF NOT EXISTS parent_comment_id BIGINT REFERENCES gw_comments(id) ON DELETE CASCADE")
        c.execute("CREATE INDEX IF NOT EXISTS gw_comments_parent_idx ON gw_comments(parent_comment_id, created_at)")
        # Phase 4: communities, memberships, discussions, events and moderation.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_communities(
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(70) NOT NULL,
            slug VARCHAR(40) NOT NULL UNIQUE,
            description VARCHAR(600) NOT NULL DEFAULT '',
            category VARCHAR(40) NOT NULL DEFAULT 'General',
            visibility VARCHAR(10) NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','private')),
            rules TEXT NOT NULL DEFAULT '',
            created_by BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_community_members(
            community_id BIGINT NOT NULL REFERENCES gw_communities(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            role VARCHAR(12) NOT NULL DEFAULT 'member' CHECK(role IN ('owner','admin','moderator','member')),
            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(community_id,user_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_community_members_user_idx ON gw_community_members(user_id,joined_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_community_requests(
            id BIGSERIAL PRIMARY KEY,
            community_id BIGINT NOT NULL REFERENCES gw_communities(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            message VARCHAR(500) NOT NULL DEFAULT '',
            status VARCHAR(12) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ,
            reviewed_by BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            UNIQUE(community_id,user_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_community_requests_pending_idx ON gw_community_requests(community_id,status,created_at)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_community_posts(
            id BIGSERIAL PRIMARY KEY,
            community_id BIGINT NOT NULL REFERENCES gw_communities(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            body VARCHAR(2000) NOT NULL DEFAULT '',
            media_url TEXT,
            media_type VARCHAR(10),
            is_announcement BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("ALTER TABLE gw_community_posts ADD COLUMN IF NOT EXISTS media_url TEXT")
        c.execute("ALTER TABLE gw_community_posts ADD COLUMN IF NOT EXISTS media_type VARCHAR(10)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_community_posts_feed_idx ON gw_community_posts(community_id,is_announcement DESC,created_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_community_events(
            id BIGSERIAL PRIMARY KEY,
            community_id BIGINT NOT NULL REFERENCES gw_communities(id) ON DELETE CASCADE,
            creator_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            title VARCHAR(100) NOT NULL,
            details VARCHAR(1000) NOT NULL DEFAULT '',
            starts_at TIMESTAMPTZ NOT NULL,
            location VARCHAR(180) NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_community_events_start_idx ON gw_community_events(community_id,starts_at)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_community_reports(
            id BIGSERIAL PRIMARY KEY,
            community_id BIGINT NOT NULL REFERENCES gw_communities(id) ON DELETE CASCADE,
            post_id BIGINT NOT NULL REFERENCES gw_community_posts(id) ON DELETE CASCADE,
            reporter_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            reason VARCHAR(40) NOT NULL,
            details VARCHAR(700) NOT NULL DEFAULT '',
            status VARCHAR(12) NOT NULL DEFAULT 'open' CHECK(status IN ('open','dismissed','actioned')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(post_id,reporter_id)
        )""")
        # Phase 5: private and group conversations.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_conversations(
            id BIGSERIAL PRIMARY KEY,
            title VARCHAR(100) NOT NULL DEFAULT '',
            is_group BOOLEAN NOT NULL DEFAULT FALSE,
            created_by BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_conversation_members(
            conversation_id BIGINT NOT NULL REFERENCES gw_conversations(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            role VARCHAR(10) NOT NULL DEFAULT 'member' CHECK(role IN ('owner','member')),
            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_read_at TIMESTAMPTZ,
            PRIMARY KEY(conversation_id,user_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_messages(
            id BIGSERIAL PRIMARY KEY,
            conversation_id BIGINT NOT NULL REFERENCES gw_conversations(id) ON DELETE CASCADE,
            sender_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            body VARCHAR(4000) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            edited_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ,
            CHECK(length(body)>0)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_conversation_members_user_idx ON gw_conversation_members(user_id,conversation_id)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_messages_conversation_idx ON gw_messages(conversation_id,created_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_conversations_updated_idx ON gw_conversations(updated_at DESC)")
        # Phase 7: private Gather AI chat history.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_ai_conversations(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            title VARCHAR(80) NOT NULL DEFAULT 'New conversation',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_ai_messages(
            id BIGSERIAL PRIMARY KEY,
            conversation_id BIGINT NOT NULL REFERENCES gw_ai_conversations(id) ON DELETE CASCADE,
            role VARCHAR(10) NOT NULL CHECK(role IN ('user','model')),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_ai_conversations_user_idx ON gw_ai_conversations(user_id, updated_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_ai_messages_conversation_idx ON gw_ai_messages(conversation_id, created_at)")
        # Phase 8: creator profiles and public business directory.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_creator_profiles(
            user_id BIGINT PRIMARY KEY REFERENCES gw_users(id) ON DELETE CASCADE,
            headline VARCHAR(120) NOT NULL DEFAULT '',
            category VARCHAR(50) NOT NULL DEFAULT 'Other',
            about VARCHAR(1200) NOT NULL DEFAULT '',
            website_url VARCHAR(500) NOT NULL DEFAULT '',
            portfolio_url VARCHAR(500) NOT NULL DEFAULT '',
            is_public BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_creator_profile_views(
            id BIGSERIAL PRIMARY KEY,
            creator_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            viewer_id BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_creator_views_creator_idx ON gw_creator_profile_views(creator_id, viewed_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_businesses(
            id BIGSERIAL PRIMARY KEY,
            owner_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            name VARCHAR(90) NOT NULL,
            slug VARCHAR(50) NOT NULL UNIQUE,
            category VARCHAR(50) NOT NULL DEFAULT 'Other',
            description VARCHAR(1500) NOT NULL DEFAULT '',
            website_url VARCHAR(500) NOT NULL DEFAULT '',
            contact_email VARCHAR(255) NOT NULL DEFAULT '',
            location VARCHAR(140) NOT NULL DEFAULT '',
            is_public BOOLEAN NOT NULL DEFAULT TRUE,
            verification_status VARCHAR(16) NOT NULL DEFAULT 'unverified',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_business_follows(
            business_id BIGINT NOT NULL REFERENCES gw_businesses(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(business_id,user_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_businesses_public_idx ON gw_businesses(is_public, created_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_business_follows_user_idx ON gw_business_follows(user_id, created_at DESC)")
        # Phase 10 preparation: affiliate partner applications and approved links.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_affiliate_partners(
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(70) NOT NULL UNIQUE,
            website_url VARCHAR(500) NOT NULL DEFAULT '',
            program_url VARCHAR(500) NOT NULL DEFAULT '',
            status VARCHAR(16) NOT NULL DEFAULT 'research'
                CHECK(status IN ('research','applied','pending','approved','rejected','paused')),
            affiliate_url TEXT,
            notes VARCHAR(1000) NOT NULL DEFAULT '',
            applied_at TIMESTAMPTZ,
            approved_at TIMESTAMPTZ,
            created_by BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK(affiliate_url IS NULL OR affiliate_url LIKE 'https://%')
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_affiliate_partners_status_idx ON gw_affiliate_partners(status, name)")
        # These application statuses were supplied by the site owner; no tracking URLs are assumed.
        c.execute("""INSERT INTO gw_affiliate_partners
            (name,slug,website_url,program_url,status,notes,applied_at)
            VALUES
            ('Daraz Pakistan','daraz-pakistan','https://www.daraz.pk/','https://www.daraz.pk/affiliate-program/','applied','Application submitted; awaiting the programme decision.',NOW()),
            ('Amazon Associates','amazon-associates','https://www.amazon.com/','https://affiliate-program.amazon.com/','applied','Application submitted; awaiting the programme decision.',NOW()),
            ('eBay Partner Network','ebay-partner-network','https://www.ebay.com/','https://partnernetwork.ebay.com/our-program','research','Research candidate; not applied.',NULL),
            ('CJ Affiliate Publisher Network','cj-affiliate','https://www.cj.com/','https://www.cj.com/join','research','Publisher network; advertiser applications are separate. Not applied.',NULL),
            ('Awin Publisher Network','awin','https://www.awin.com/','https://www.awin.com/','research','Publisher network; individual advertiser approval may be required. Not applied.',NULL),
            ('Impact Affiliate Publisher Network','impact-com','https://impact.com/','https://impact.com/','research','Publisher platform; individual brand approvals may be required. Not applied.',NULL),
            ('Admitad Publisher Network','admitad','https://www.admitad.com/','https://www.admitad.com/','research','Publisher and creator network; programme availability varies. Not applied.',NULL),
            ('Namecheap Affiliate Program','namecheap','https://www.namecheap.com/','https://www.namecheap.com/affiliates/','research','Direct programme; approval and payment eligibility must be checked. Not applied.',NULL),
            ('Hostinger Affiliate Program','hostinger','https://www.hostinger.com/','https://www.hostinger.com/affiliates','research','Direct programme; approval and payment eligibility must be checked. Not applied.',NULL),
            ('Envato Market Affiliate Program','envato-market','https://market.envato.com/','https://help.market.envato.com/hc/en-us/articles/11695049571609-How-do-I-become-an-Envato-Market-affiliate','research','Envato Market has a separate affiliate programme from Elements and Placeit. Not applied.',NULL),
            ('Booking.com Affiliate Program','booking-com','https://www.booking.com/','https://www.booking.com/affiliate-program/v2/index.html','research','Official page directs partners through affiliate networks such as Awin or CJ. Not applied.',NULL)
            ON CONFLICT (slug) DO NOTHING""")
        # Phase 11: user shopping tools and manually curated affiliate product catalogue.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_shop_products(
            id BIGSERIAL PRIMARY KEY,
            partner_id BIGINT NOT NULL REFERENCES gw_affiliate_partners(id) ON DELETE RESTRICT,
            title VARCHAR(140) NOT NULL,
            slug VARCHAR(170) NOT NULL UNIQUE,
            description VARCHAR(4000) NOT NULL DEFAULT '',
            category VARCHAR(60) NOT NULL DEFAULT 'Other',
            image_url TEXT NOT NULL DEFAULT '',
            currency CHAR(3) NOT NULL DEFAULT 'USD',
            partner_price NUMERIC(12,2) NOT NULL CHECK(partner_price >= 0),
            original_price NUMERIC(12,2),
            affiliate_url TEXT,
            status VARCHAR(12) NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','paused')),
            created_by BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK(original_price IS NULL OR original_price >= partner_price),
            CHECK(image_url = '' OR image_url LIKE 'https://%'),
            CHECK(affiliate_url IS NULL OR affiliate_url LIKE 'https://%')
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_products_public_idx ON gw_shop_products(status, category, updated_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_products_partner_idx ON gw_shop_products(partner_id, status)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_shop_cart_items(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            product_id BIGINT NOT NULL REFERENCES gw_shop_products(id) ON DELETE CASCADE,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity BETWEEN 1 AND 10),
            added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_cart_user_idx ON gw_shop_cart_items(user_id, added_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_shop_wishlists(
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            product_id BIGINT NOT NULL REFERENCES gw_shop_products(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, product_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_wishlist_user_idx ON gw_shop_wishlists(user_id, created_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_shop_price_alerts(
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            product_id BIGINT NOT NULL REFERENCES gw_shop_products(id) ON DELETE CASCADE,
            target_price NUMERIC(12,2) NOT NULL CHECK(target_price >= 0),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            notified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_price_alerts_product_idx ON gw_shop_price_alerts(product_id, is_active)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_shop_product_views(
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES gw_shop_products(id) ON DELETE CASCADE,
            user_id BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_product_views_user_idx ON gw_shop_product_views(user_id, viewed_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_shop_product_clicks(
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL REFERENCES gw_shop_products(id) ON DELETE CASCADE,
            user_id BIGINT REFERENCES gw_users(id) ON DELETE SET NULL,
            clicked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_shop_product_clicks_product_idx ON gw_shop_product_clicks(product_id,clicked_at DESC)")
        # Phases 12–17: one consistent, lightweight directory foundation for services,
        # food/local commerce, travel, learning resources, jobs and events.
        c.execute("""CREATE TABLE IF NOT EXISTS gw_directory_entries(
            id BIGSERIAL PRIMARY KEY,
            entry_kind VARCHAR(16) NOT NULL CHECK(entry_kind IN ('service','food','travel','education','job','event')),
            owner_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            title VARCHAR(140) NOT NULL,
            slug VARCHAR(170) NOT NULL,
            category VARCHAR(70) NOT NULL DEFAULT 'Other',
            summary VARCHAR(260) NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            location VARCHAR(180) NOT NULL DEFAULT '',
            price_label VARCHAR(80) NOT NULL DEFAULT '',
            external_url TEXT NOT NULL DEFAULT '',
            contact_email VARCHAR(255) NOT NULL DEFAULT '',
            image_url TEXT NOT NULL DEFAULT '',
            event_starts_at TIMESTAMPTZ,
            event_ends_at TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_featured BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(entry_kind, slug),
            CHECK(external_url = '' OR external_url LIKE 'https://%'),
            CHECK(image_url = '' OR image_url LIKE 'https://%'),
            CHECK(contact_email = '' OR contact_email LIKE '%@%')
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_directory_kind_active_idx ON gw_directory_entries(entry_kind,is_active,created_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_directory_owner_idx ON gw_directory_entries(owner_id,created_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS gw_directory_category_idx ON gw_directory_entries(entry_kind,category,is_active)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_directory_event_rsvps(
            entry_id BIGINT NOT NULL REFERENCES gw_directory_entries(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            response VARCHAR(12) NOT NULL CHECK(response IN ('going','interested')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(entry_id,user_id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_directory_event_rsvp_user_idx ON gw_directory_event_rsvps(user_id,updated_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS gw_service_inquiries(
            id BIGSERIAL PRIMARY KEY,
            entry_id BIGINT NOT NULL REFERENCES gw_directory_entries(id) ON DELETE CASCADE,
            sender_id BIGINT NOT NULL REFERENCES gw_users(id) ON DELETE CASCADE,
            message VARCHAR(1800) NOT NULL,
            status VARCHAR(12) NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS gw_service_inquiries_entry_idx ON gw_service_inquiries(entry_id,created_at DESC)")
        c.execute("DELETE FROM gw_rate_limits WHERE window_started_at < NOW() - INTERVAL '2 days'")
def user(uid=None):
    uid = uid or session.get("user_id")
    if not uid:
        return None
    with db() as c:
        return c.execute("""SELECT id,username,email,display_name,bio,avatar_url,avatar_preset,
            created_at,is_verified,is_suspended,suspended_reason,session_version
            FROM gw_users WHERE id=%s""", (uid,)).fetchone()

def is_admin(account=None):
    account = account or user()
    if not account:
        return False
    return account["username"].lower() in ADMIN_USERNAMES or account["email"].lower() in ADMIN_EMAILS

def create_notification(conn, recipient_id, actor_id, notification_type, entity_type=None, entity_id=None, message=""):
    """Create an in-app notification without notifying a user about their own action."""
    if not recipient_id or not actor_id or int(recipient_id) == int(actor_id):
        return
    conn.execute(
        """INSERT INTO gw_notifications
           (recipient_id, actor_id, notification_type, entity_type, entity_id, message)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (recipient_id, actor_id, notification_type, entity_type, entity_id, (message or "You have a new notification")[:240]),
    )


def post_visibility_query(viewer_id):
    """SQL fragment is intentionally fixed; caller supplies viewer_id separately."""
    return "NOT EXISTS (SELECT 1 FROM gw_user_blocks b WHERE (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))"


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token

@app.before_request
def protect_state_changes():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        expected = session.get("_csrf_token", "")
        supplied = request.form.get("_csrf_token", "") or request.headers.get("X-CSRF-Token", "")
        if not expected or not supplied or not secrets.compare_digest(expected, supplied):
            abort(400, description="The form security token is missing or expired. Refresh the page and try again.")

@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

def rate_limit_allowed(action, limit, window_seconds, identity=""):
    """Database-backed fixed-window limiter. Keys are hashed; raw IPs/emails are not stored."""
    remote = request.remote_addr or "unknown"
    raw = f"{action}|{remote}|{identity}".lower().encode("utf-8")
    key = hashlib.sha256(raw).hexdigest()
    with db() as c:
        row = c.execute("""INSERT INTO gw_rate_limits(bucket_key,window_started_at,hits)
            VALUES(%s,NOW(),1)
            ON CONFLICT(bucket_key) DO UPDATE SET
              hits=CASE WHEN gw_rate_limits.window_started_at <= NOW() - (%s * INTERVAL '1 second')
                        THEN 1 ELSE gw_rate_limits.hits+1 END,
              window_started_at=CASE WHEN gw_rate_limits.window_started_at <= NOW() - (%s * INTERVAL '1 second')
                        THEN NOW() ELSE gw_rate_limits.window_started_at END
            RETURNING hits""", (key, window_seconds, window_seconds)).fetchone()
    return row["hits"] <= limit

def admin_required(fn):
    @wraps(fn)
    @required
    def wrapped(*args, **kwargs):
        account = user()
        if not is_admin(account):
            abort(403)
        return fn(*args, **kwargs)
    return wrapped

def required(fn):
    @wraps(fn)
    def w(*a,**k):
        uid = session.get("user_id")
        if not uid:
            flash("Please log in first.", "info")
            return redirect(url_for("login"))
        account = user(uid)
        if not account or account["is_suspended"]:
            session.clear()
            flash("This account is unavailable. Contact Gather World support if you need help.", "error")
            return redirect(url_for("login"))
        if session.get("session_version") != account["session_version"]:
            session.clear()
            flash("Your session has expired. Please log in again.", "info")
            return redirect(url_for("login"))
        return fn(*a,**k)
    return w

@app.context_processor
def ctx():
    try:
        account = user()
        unread_notifications = 0
        if account:
            with db() as c:
                row = c.execute("SELECT COUNT(*) AS n FROM gw_notifications WHERE recipient_id=%s AND is_read=FALSE", (account["id"],)).fetchone()
                unread_notifications = row["n"] if row else 0
                message_row = c.execute("""SELECT COUNT(*) AS n
                    FROM gw_messages m JOIN gw_conversation_members cm ON cm.conversation_id=m.conversation_id
                    WHERE cm.user_id=%s AND m.sender_id<>%s AND m.deleted_at IS NULL
                      AND (cm.last_read_at IS NULL OR m.created_at>cm.last_read_at)""", (account["id"], account["id"])).fetchone()
                unread_messages = message_row["n"] if message_row else 0
        else:
            unread_messages = 0
        return {"current_user": account, "avatar_presets": AVATAR_PRESETS,
                "current_user_is_admin": is_admin(account), "admin_usernames": ADMIN_USERNAMES,
                "admin_emails": ADMIN_EMAILS, "csrf_token": csrf_token,
                "unread_notifications": unread_notifications, "unread_messages": unread_messages}
    except Exception:
        return {"current_user": None, "avatar_presets": AVATAR_PRESETS,
                "current_user_is_admin": False, "admin_usernames": ADMIN_USERNAMES,
                "admin_emails": ADMIN_EMAILS, "csrf_token": csrf_token,
                "unread_notifications": 0, "unread_messages": 0}

@app.route("/")
def home():
    try:
        with db() as c:s=c.execute("SELECT (SELECT COUNT(*) FROM gw_users) users,(SELECT COUNT(*) FROM gw_posts) posts").fetchone()
    except Exception:s=None
    return render_template("home.html",stats=s)
@app.route("/health")
def health():
    try:
        with db() as c:c.execute("SELECT 1")
        return jsonify(status="ok",database="connected")
    except:return jsonify(status="error",database="unavailable"),503
def send_gather_email(to_email, subject, html_body, text_body):
    """Send mail through configured Zoho SMTP. Credentials stay in environment variables."""
    if not all((MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER)):
        raise RuntimeError("Zoho SMTP is not configured. Set MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD and MAIL_DEFAULT_SENDER.")
    msg=EmailMessage()
    msg["Subject"]=subject
    msg["From"]=MAIL_DEFAULT_SENDER
    msg["To"]=to_email
    msg.set_content(text_body)
    msg.add_alternative(html_body,subtype="html")
    context=ssl.create_default_context()
    if MAIL_PORT==465:
        with smtplib.SMTP_SSL(MAIL_SERVER,MAIL_PORT,context=context,timeout=20) as server:
            server.login(MAIL_USERNAME,MAIL_PASSWORD)
            server.send_message(msg)
    else:
        with smtplib.SMTP(MAIL_SERVER,MAIL_PORT,timeout=20) as server:
            server.ehlo()
            if MAIL_USE_TLS:
                server.starttls(context=context)
                server.ehlo()
            server.login(MAIL_USERNAME,MAIL_PASSWORD)
            server.send_message(msg)


def send_verification_code(user_id,email,allow_resend=False):
    code=f"{secrets.randbelow(900000)+100000:06d}"
    now=datetime.now(timezone.utc)
    with db() as c:
        old=c.execute("SELECT last_sent_at FROM gw_email_otps WHERE user_id=%s",(user_id,)).fetchone()
        if old and not allow_resend:
            raise RuntimeError("A verification code has already been created.")
        if old and allow_resend and old["last_sent_at"] and now-old["last_sent_at"]<timedelta(seconds=60):
            raise ValueError("Please wait 60 seconds before requesting another code.")
        c.execute("""INSERT INTO gw_email_otps(user_id,code_hash,expires_at,attempts,last_sent_at)
            VALUES(%s,%s,%s,0,%s)
            ON CONFLICT(user_id) DO UPDATE SET code_hash=EXCLUDED.code_hash,
            expires_at=EXCLUDED.expires_at,attempts=0,last_sent_at=EXCLUDED.last_sent_at""",
            (user_id,generate_password_hash(code),now+timedelta(minutes=10),now))
    html=f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:28px;background:#101a2d;color:#f4f6ff;border-radius:16px'><p style='letter-spacing:3px;color:#82cfff;font-size:12px'>GATHER WORLD</p><h2>Verify your email</h2><p>Enter this code on Gather World to finish creating your account.</p><div style='font-size:32px;font-weight:800;letter-spacing:9px;padding:18px;background:#1c2a45;border-radius:12px;text-align:center'>{code}</div><p>This code expires in 10 minutes. If you did not request it, you can ignore this email.</p></div>"
    send_gather_email(email,"Your Gather World verification code",html,f"Your Gather World verification code is {code}. It expires in 10 minutes.")


def password_reset_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        if not rate_limit_allowed("register", 5, 3600):
            flash("Too many registration attempts. Please try again later.", "error")
            return render_template("register.html"), 429
        u=request.form.get("username"," ").strip().lower();e=request.form.get("email","").strip().lower();d=request.form.get("display_name","").strip();p=request.form.get("password","");confirm=request.form.get("confirm_password","")
        if not re.fullmatch(r"[a-z0-9_]{3,30}",u):flash("Username: 3–30 letters, numbers or underscores.","error")
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):flash("Enter a valid email.","error")
        elif not d or len(d)>60:flash("Display name is required (max 60).","error")
        elif len(p)<10:flash("Password must be at least 10 characters.","error")
        elif p!=confirm:flash("The passwords do not match.","error")
        else:
            try:
                with db() as c:r=c.execute("INSERT INTO gw_users(username,email,password_hash,display_name,is_verified) VALUES(%s,%s,%s,%s,FALSE) RETURNING id,email",(u,e,generate_password_hash(p),d)).fetchone()
                session.clear();session["pending_user_id"]=r["id"]
                try:
                    send_verification_code(r["id"],r["email"])
                    flash("Your account is created. Enter the six-digit code sent to your email.","success")
                except Exception:
                    app.logger.exception("verification email could not be sent")
                    flash("Your account is saved but the verification email could not be sent. Configure Zoho SMTP, then use Resend code.","error")
                return redirect(url_for("verify_email"))
            except psycopg.errors.UniqueViolation:flash("Username or email already exists.","error")
            except Exception:app.logger.exception("register");flash("Registration failed. Check Neon settings.","error")
    return render_template("register.html")


@app.route("/verify-email",methods=["GET","POST"])
def verify_email():
    pending_id=session.get("pending_user_id")
    if not pending_id:
        flash("Start registration or log in to verify your email.","info")
        return redirect(url_for("register"))
    if request.method=="POST":
        if not rate_limit_allowed("verify_email", 8, 600, str(pending_id)):
            flash("Too many verification attempts. Please try again later.", "error")
            return render_template("verify_email.html"), 429
        code=request.form.get("code","").strip()
        if not re.fullmatch(r"[0-9]{6}",code):
            flash("Enter the six-digit verification code.","error")
        else:
            with db() as c:
                record=c.execute("SELECT code_hash,expires_at,attempts FROM gw_email_otps WHERE user_id=%s",(pending_id,)).fetchone()
                if not record:
                    flash("No active code was found. Request a new code.","error")
                elif record["attempts"]>=5:
                    flash("Too many incorrect attempts. Request a new code.","error")
                elif record["expires_at"]<datetime.now(timezone.utc):
                    flash("That code has expired. Request a new code.","error")
                elif not check_password_hash(record["code_hash"],code):
                    c.execute("UPDATE gw_email_otps SET attempts=attempts+1 WHERE user_id=%s",(pending_id,))
                    flash("That code is incorrect. Please try again.","error")
                else:
                    c.execute("UPDATE gw_users SET is_verified=TRUE WHERE id=%s",(pending_id,))
                    c.execute("DELETE FROM gw_email_otps WHERE user_id=%s",(pending_id,))
                    version_row = c.execute("SELECT session_version FROM gw_users WHERE id=%s", (pending_id,)).fetchone()
                    session.clear();session["user_id"]=pending_id;session["session_version"]=version_row["session_version"];session.permanent=True
                    flash("Email verified. Welcome to Gather World!","success")
                    return redirect(url_for("feed"))
    return render_template("verify_email.html")


@app.post("/resend-otp")
def resend_otp():
    pending_id=session.get("pending_user_id")
    if not pending_id:
        flash("Start registration or log in first.","info")
        return redirect(url_for("register"))
    if not rate_limit_allowed("resend_otp", 5, 3600, str(pending_id)):
        flash("Too many code requests. Please try again later.", "error")
        return redirect(url_for("verify_email"))
    try:
        with db() as c:r=c.execute("SELECT email,is_verified FROM gw_users WHERE id=%s",(pending_id,)).fetchone()
        if not r or r["is_verified"]:
            session.pop("pending_user_id",None)
            flash("This account does not need verification.","info")
            return redirect(url_for("login"))
        send_verification_code(pending_id,r["email"],allow_resend=True)
        flash("A new verification code has been sent.","success")
    except ValueError as exc:flash(str(exc),"error")
    except Exception:
        app.logger.exception("resend verification email failed")
        flash("Could not send the code. Check the Zoho SMTP settings.","error")
    return redirect(url_for("verify_email"))


@app.route("/forgot-password",methods=["GET","POST"])
def forgot_password():
    if request.method=="POST":
        if not rate_limit_allowed("forgot_password", 3, 3600):
            flash("Too many reset requests. Please try again later.", "error")
            return render_template("forgot_password.html"), 429
        email=request.form.get("email","").strip().lower()
        # The same confirmation is shown whether or not the address exists.
        try:
            with db() as c:r=c.execute("SELECT id,email FROM gw_users WHERE email=%s AND is_verified=TRUE",(email,)).fetchone()
            if r:
                token=secrets.token_urlsafe(32)
                with db() as c:
                    c.execute("INSERT INTO gw_password_resets(user_id,token_hash,expires_at) VALUES(%s,%s,%s)",(r["id"],password_reset_token_hash(token),datetime.now(timezone.utc)+timedelta(minutes=30)))
                link=url_for("reset_password",token=token,_external=True)
                html=f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:28px;background:#101a2d;color:#f4f6ff;border-radius:16px'><p style='letter-spacing:3px;color:#82cfff;font-size:12px'>GATHER WORLD</p><h2>Reset your password</h2><p>Use the button below to choose a new password. This link expires in 30 minutes.</p><p><a href='{link}' style='display:inline-block;padding:13px 20px;background:#269ee5;color:white;text-decoration:none;border-radius:8px'>Reset password</a></p><p>If you did not request this, ignore this email.</p></div>"
                send_gather_email(r["email"],"Reset your Gather World password",html,f"Reset your Gather World password using this link: {link} . The link expires in 30 minutes.")
        except Exception:app.logger.exception("password reset email request failed")
        flash("If a verified account uses that email, a password reset link will be sent.","success")
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>",methods=["GET","POST"])
def reset_password(token):
    token_hash=password_reset_token_hash(token)
    with db() as c:r=c.execute("SELECT id,user_id FROM gw_password_resets WHERE token_hash=%s AND used_at IS NULL AND expires_at>NOW()",(token_hash,)).fetchone()
    if not r:
        flash("This password reset link is invalid, expired or already used.","error")
        return redirect(url_for("forgot_password"))
    if request.method=="POST":
        if not rate_limit_allowed("reset_password", 5, 3600, str(r["user_id"])):
            flash("Too many password reset attempts. Please try again later.", "error")
            return render_template("reset_password.html"), 429
        p=request.form.get("password","");confirm=request.form.get("confirm_password","")
        if len(p)<10:flash("Password must be at least 10 characters.","error")
        elif p!=confirm:flash("The passwords do not match.","error")
        else:
            with db() as c:
                c.execute("UPDATE gw_users SET password_hash=%s,session_version=session_version+1 WHERE id=%s",(generate_password_hash(p),r["user_id"]))
                c.execute("UPDATE gw_password_resets SET used_at=NOW() WHERE user_id=%s AND used_at IS NULL",(r["user_id"],))
            flash("Your password has been changed. Please log in.","success")
            return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        ident=request.form.get("identity","").strip().lower();p=request.form.get("password","")
        if not rate_limit_allowed("login", 10, 900, ident):
            flash("Too many login attempts. Please wait before trying again.", "error")
            return render_template("login.html"), 429
        try:
            with db() as c:r=c.execute("SELECT id,password_hash,is_verified,is_suspended,session_version FROM gw_users WHERE username=%s OR email=%s",(ident,ident)).fetchone()
            if r and check_password_hash(r["password_hash"],p):
                if r["is_suspended"]:
                    flash("This account is suspended. Contact Gather World support for assistance.", "error")
                    return render_template("login.html"), 403
                if not r["is_verified"]:
                    session.clear();session["pending_user_id"]=r["id"]
                    flash("Please verify your email before logging in.","info")
                    return redirect(url_for("verify_email"))
                session.clear();session["user_id"]=r["id"];session["session_version"]=r["session_version"];session.permanent=True
                return redirect(url_for("feed"))
            flash("Incorrect username/email or password.","error")
        except Exception:app.logger.exception("login");flash("Login unavailable.","error")
    return render_template("login.html")
@app.post("/logout")
def logout():session.clear();return redirect(url_for("home"))
def upload_avatar_to_cloudinary(upload):
    """Upload a profile photo directly from Flask to Cloudinary; no local file is saved."""
    if not all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)):
        raise RuntimeError("Cloudinary is not configured yet. Add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET to your local .env.")
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True,
        )
        result = cloudinary.uploader.upload(
            upload,
            folder="gather-world/avatars",
            resource_type="image",
            allowed_formats=["jpg", "jpeg", "png", "webp"],
            transformation=[{"width": 600, "height": 600, "crop": "fill", "gravity": "auto"}],
        )
        secure_url = result.get("secure_url")
        if not secure_url or not secure_url.startswith("https://"):
            raise RuntimeError("Cloudinary did not return a secure image URL.")
        return secure_url
    except ImportError as exc:
        raise RuntimeError("Cloudinary package is missing. Run: pip install -r requirements.txt") from exc


def upload_post_media_to_cloudinary(upload, media_type):
    """Upload a post image or video directly to Cloudinary; never save it locally."""
    if not all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)):
        raise RuntimeError("Cloudinary is not configured. Add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET to your private .env file.")
    try:
        import cloudinary
        import cloudinary.uploader
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True,
        )
        if media_type == "image":
            folder = "gather-world/posts/images"
            resource_type = "image"
            formats = ["jpg", "jpeg", "png", "webp"]
        elif media_type == "video":
            folder = "gather-world/posts/videos"
            resource_type = "video"
            formats = ["mp4", "mov", "webm", "m4v"]
        else:
            raise RuntimeError("Choose a photo or video file.")
        result = cloudinary.uploader.upload(
            upload,
            folder=folder,
            resource_type=resource_type,
            allowed_formats=formats,
            unique_filename=True,
            overwrite=False,
        )
        secure_url = result.get("secure_url")
        if not secure_url or not secure_url.startswith("https://"):
            raise RuntimeError("Cloudinary did not return a secure media URL.")
        return secure_url
    except ImportError as exc:
        raise RuntimeError("Cloudinary package is missing. Run: pip install -r requirements.txt") from exc



@app.route("/profile/edit",methods=["GET","POST"])
@required
def edit_profile():
    me = user()
    if request.method == "POST":
        new_username = request.form.get("username", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "").strip()
        upload = request.files.get("avatar_file")
        selected = request.form.get("avatar_preset", "").strip()

        if not re.fullmatch(r"[a-z0-9_]{3,30}", new_username):
            flash("Username must be 3–30 characters using lowercase letters, numbers or underscores.", "error")
        elif not display_name or len(display_name) > 60 or len(bio) > 300:
            flash("Check display name and bio lengths.", "error")
        else:
            try:
                with db() as c:
                    duplicate = c.execute(
                        "SELECT id FROM gw_users WHERE username=%s AND id<>%s",
                        (new_username, session["user_id"]),
                    ).fetchone()
                if duplicate:
                    flash("That username is already taken. Please choose another.", "error")
                else:
                    avatar_url = me["avatar_url"]
                    avatar_preset = me["avatar_preset"]
                    if upload and upload.filename:
                        extension = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
                        if extension not in {"jpg", "jpeg", "png", "webp"} or upload.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
                            flash("Choose a JPG, PNG or WEBP image for your display picture.", "error")
                            return render_template("edit.html", me=me)
                        upload.stream.seek(0, os.SEEK_END)
                        size = upload.stream.tell()
                        upload.stream.seek(0)
                        if size > 5 * 1024 * 1024:
                            flash("Your display picture must be 5 MB or smaller.", "error")
                            return render_template("edit.html", me=me)
                        avatar_url = upload_avatar_to_cloudinary(upload.stream)
                    elif selected:
                        if selected not in AVATAR_PRESETS:
                            flash("Please choose one of the available Gather avatars.", "error")
                            return render_template("edit.html", me=me)
                        avatar_preset = selected
                        avatar_url = None

                    with db() as c:
                        c.execute(
                            """UPDATE gw_users
                               SET username=%s, display_name=%s, bio=%s,
                                   avatar_url=%s, avatar_preset=%s
                               WHERE id=%s""",
                            (new_username, display_name, bio, avatar_url, avatar_preset, session["user_id"]),
                        )
                    flash("Your username and profile have been updated.", "success")
                    if me["username"].lower() in ADMIN_USERNAMES and new_username != me["username"].lower():
                        flash("Because your old username was configured as an admin, update ADMIN_USERNAMES in your private .env to the new username and restart Flask to keep admin access.", "info")
                    return redirect(url_for("public_profile", username=new_username))
            except psycopg.errors.UniqueViolation:
                flash("That username is already taken. Please choose another.", "error")
            except Exception as exc:
                app.logger.exception("Profile update failed")
                flash(str(exc) if isinstance(exc, RuntimeError) else "Your profile could not be updated. Please try again.", "error")
    return render_template("edit.html", me=me)
@app.route("/profile")
@required
def profile():return redirect(url_for("public_profile",username=user()["username"]))
@app.route("/u/<username>")
def public_profile(username):
    with db() as c:
        u=c.execute("""SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset,u.created_at,u.is_suspended,
            (SELECT COUNT(*) FROM gw_follows WHERE followed_id=u.id) followers,
            (SELECT COUNT(*) FROM gw_follows WHERE follower_id=u.id) following
            FROM gw_users u WHERE username=%s""",(username.lower(),)).fetchone()
        if not u or u["is_suspended"]:return render_template("404.html"),404
        viewer_id=session.get("user_id",-1)
        if viewer_id>0 and viewer_id!=u["id"] and c.execute("SELECT 1 FROM gw_user_blocks WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)",(viewer_id,u["id"],u["id"],viewer_id)).fetchone():
            return render_template("404.html"),404
        posts=c.execute("""SELECT p.*,(SELECT COUNT(*) FROM gw_likes WHERE post_id=p.id) likes,(SELECT COUNT(*) FROM gw_comments WHERE post_id=p.id) comments,
            EXISTS(SELECT 1 FROM gw_likes WHERE post_id=p.id AND user_id=%s) liked,
            EXISTS(SELECT 1 FROM gw_bookmarks WHERE post_id=p.id AND user_id=%s) bookmarked
            FROM gw_posts p WHERE user_id=%s ORDER BY created_at DESC LIMIT 50""",(viewer_id,viewer_id,u["id"])).fetchall()
        following=bool(session.get("user_id") and session["user_id"]!=u["id"] and c.execute("SELECT 1 FROM gw_follows WHERE follower_id=%s AND followed_id=%s",(session.get("user_id"),u["id"])).fetchone())
    return render_template("public.html",u=u,posts=posts,following=following)
@app.route("/members")
def members():
    q=request.args.get("q","").strip()[:50]
    viewer_id = session.get("user_id", -1)
    with db() as c:rows=c.execute("""SELECT u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset
        FROM gw_users u WHERE u.is_suspended=FALSE AND (%s='' OR u.username ILIKE %s OR u.display_name ILIKE %s)
        AND (%s<1 OR NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
          (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s)))
        ORDER BY u.created_at DESC LIMIT 100""",(q,"%"+q+"%","%"+q+"%",viewer_id,viewer_id,viewer_id)).fetchall()
    return render_template("members.html",rows=rows,q=q)
# ---------------------------- PHASE 4: COMMUNITIES ----------------------------
COMMUNITY_CATEGORIES = (
    "General", "Technology", "Gaming", "Photography", "Sports", "Travel",
    "Music", "Education", "Programming", "Art & Design", "Books", "Lifestyle",
)

def community_member_role(conn, community_id, account_id):
    if not account_id or int(account_id) < 1:
        return None
    row = conn.execute(
        "SELECT role FROM gw_community_members WHERE community_id=%s AND user_id=%s",
        (community_id, account_id),
    ).fetchone()
    return row["role"] if row else None

def community_staff(role):
    return role in {"owner", "admin", "moderator"}

def get_community_or_404(conn, slug):
    community = conn.execute("SELECT * FROM gw_communities WHERE slug=%s", (slug.lower(),)).fetchone()
    if not community:
        abort(404)
    return community

@app.route("/communities")
def community_list():
    q = request.args.get("q", "").strip()[:60]
    category = request.args.get("category", "").strip()[:40]
    viewer_id = session.get("user_id", -1)
    with db() as c:
        rows = c.execute("""SELECT cmn.*,
            (SELECT COUNT(*) FROM gw_community_members m WHERE m.community_id=cmn.id) AS member_count,
            EXISTS(SELECT 1 FROM gw_community_members mine WHERE mine.community_id=cmn.id AND mine.user_id=%s) AS joined,
            u.username AS creator_username,u.display_name AS creator_name
            FROM gw_communities cmn JOIN gw_users u ON u.id=cmn.created_by
            WHERE (cmn.visibility='public' OR EXISTS(
                SELECT 1 FROM gw_community_members mine WHERE mine.community_id=cmn.id AND mine.user_id=%s
            ))
            AND (%s='' OR cmn.name ILIKE %s OR cmn.slug ILIKE %s OR cmn.description ILIKE %s)
            AND (%s='' OR cmn.category=%s)
            ORDER BY member_count DESC,cmn.created_at DESC LIMIT 100""",
            (viewer_id, viewer_id, q, "%"+q+"%", "%"+q+"%", "%"+q+"%", category, category)).fetchall()
    return render_template("communities.html", communities=rows, q=q, selected_category=category, categories=COMMUNITY_CATEGORIES)

@app.route("/communities/create", methods=["GET", "POST"])
@required
def community_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        slug = request.form.get("slug", "").strip().lower()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "General").strip()
        visibility = request.form.get("visibility", "public").strip().lower()
        rules = request.form.get("rules", "").strip()[:3000]
        if not (3 <= len(name) <= 70):
            flash("Community name must be between 3 and 70 characters.", "error")
        elif not re.fullmatch(r"[a-z0-9-]{3,40}", slug):
            flash("Community address must use 3–40 lowercase letters, numbers or hyphens.", "error")
        elif len(description) > 600 or visibility not in {"public", "private"} or category not in COMMUNITY_CATEGORIES:
            flash("Please check the community details and try again.", "error")
        elif not rate_limit_allowed("create_community", 5, 86400, str(session.get("user_id"))):
            flash("You have reached the daily community creation limit.", "error")
        else:
            try:
                with db() as c:
                    created = c.execute("""INSERT INTO gw_communities(name,slug,description,category,visibility,rules,created_by)
                        VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (name, slug, description, category, visibility, rules, session["user_id"])).fetchone()
                    c.execute("INSERT INTO gw_community_members(community_id,user_id,role) VALUES(%s,%s,'owner')",
                        (created["id"], session["user_id"]))
                flash("Your community has been created.", "success")
                return redirect(url_for("community_view", slug=slug))
            except psycopg.errors.UniqueViolation:
                flash("That community address is already taken. Choose another.", "error")
    return render_template("community_create.html", categories=COMMUNITY_CATEGORIES)

@app.route("/community/<slug>")
def community_view(slug):
    viewer_id = session.get("user_id", -1)
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], viewer_id)
        count = c.execute("SELECT COUNT(*) AS n FROM gw_community_members WHERE community_id=%s", (community["id"],)).fetchone()["n"]
        pending = None
        if viewer_id > 0 and not role:
            pending = c.execute("SELECT status FROM gw_community_requests WHERE community_id=%s AND user_id=%s", (community["id"], viewer_id)).fetchone()
        if community["visibility"] == "private" and not role:
            posts = []
            events = []
            members = []
            requests = []
        else:
            posts = c.execute("""SELECT p.*,u.username,u.display_name,u.avatar_url,u.avatar_preset
                FROM gw_community_posts p JOIN gw_users u ON u.id=p.user_id
                WHERE p.community_id=%s AND u.is_suspended=FALSE
                ORDER BY p.is_announcement DESC,p.created_at DESC LIMIT 60""", (community["id"],)).fetchall()
            events = c.execute("""SELECT e.*,u.username AS creator_username FROM gw_community_events e
                JOIN gw_users u ON u.id=e.creator_id WHERE e.community_id=%s AND e.starts_at>=NOW()
                ORDER BY e.starts_at ASC LIMIT 10""", (community["id"],)).fetchall()
            members = c.execute("""SELECT u.id,u.username,u.display_name,u.avatar_url,u.avatar_preset,m.role
                FROM gw_community_members m JOIN gw_users u ON u.id=m.user_id
                WHERE m.community_id=%s ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 WHEN 'moderator' THEN 2 ELSE 3 END,m.joined_at LIMIT 30""", (community["id"],)).fetchall()
            requests = []
            reports = []
            if community_staff(role):
                requests = c.execute("""SELECT r.id,r.message,r.created_at,u.username,u.display_name
                    FROM gw_community_requests r JOIN gw_users u ON u.id=r.user_id
                    WHERE r.community_id=%s AND r.status='pending' ORDER BY r.created_at ASC LIMIT 40""", (community["id"],)).fetchall()
                reports = c.execute("""SELECT r.id,r.reason,r.details,r.created_at,p.body,u.username AS reporter_username
                    FROM gw_community_reports r JOIN gw_community_posts p ON p.id=r.post_id
                    JOIN gw_users u ON u.id=r.reporter_id WHERE r.community_id=%s AND r.status='open'
                    ORDER BY r.created_at ASC LIMIT 40""", (community["id"],)).fetchall()
        if community["visibility"] == "private" and not role:
            reports = []
    return render_template("community_view.html", community=community, role=role, member_count=count,
        pending_request=pending, posts=posts, events=events, members=members, requests=requests,
        reports=reports, is_staff=community_staff(role))

@app.post("/community/<slug>/join")
@required
def community_join(slug):
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if role:
            flash("You are already a member of this community.", "info")
        elif community["visibility"] == "public":
            c.execute("INSERT INTO gw_community_members(community_id,user_id,role) VALUES(%s,%s,'member') ON CONFLICT DO NOTHING",
                (community["id"], session["user_id"]))
            create_notification(c, community["created_by"], session["user_id"], "community_join", "community", community["id"], "joined your community")
            flash("You joined the community.", "success")
        else:
            message = request.form.get("message", "").strip()[:500]
            c.execute("""INSERT INTO gw_community_requests(community_id,user_id,message,status,created_at,reviewed_at,reviewed_by)
                VALUES(%s,%s,%s,'pending',NOW(),NULL,NULL)
                ON CONFLICT(community_id,user_id) DO UPDATE SET message=EXCLUDED.message,status='pending',created_at=NOW(),reviewed_at=NULL,reviewed_by=NULL""",
                (community["id"], session["user_id"], message))
            create_notification(c, community["created_by"], session["user_id"], "community_request", "community", community["id"], "requested to join your private community")
            flash("Your membership request has been sent.", "success")
    return redirect(url_for("community_view", slug=slug))

@app.post("/community/<slug>/leave")
@required
def community_leave(slug):
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if role == "owner":
            flash("The community owner cannot leave. Transfer ownership first.", "error")
        elif role:
            c.execute("DELETE FROM gw_community_members WHERE community_id=%s AND user_id=%s", (community["id"], session["user_id"]))
            flash("You left the community.", "success")
        else:
            flash("You are not a member of this community.", "info")
    return redirect(url_for("community_view", slug=slug))

@app.post("/community/<slug>/posts")
@required
def community_create_post(slug):
    body = request.form.get("body", "").strip()
    media_file = request.files.get("media_file")
    media_url = None
    media_type = None
    if len(body) > 2000:
        flash("Your discussion text must be 2,000 characters or fewer.", "error")
        return redirect(url_for("community_view", slug=slug))
    with db() as c:
        community_check = get_community_or_404(c, slug)
        if not community_member_role(c, community_check["id"], session["user_id"]):
            abort(403)
    if media_file and media_file.filename:
        filename = media_file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mime = (media_file.mimetype or "").lower()
        if extension in {"jpg", "jpeg", "png", "webp"} and mime in {"image/jpeg", "image/png", "image/webp", "application/octet-stream"}:
            media_type, max_bytes = "image", 10 * 1024 * 1024
        elif extension in {"mp4", "m4v", "mov", "webm"} and mime in {"video/mp4", "video/x-m4v", "video/quicktime", "video/webm", "application/mp4", "application/octet-stream"}:
            media_type, max_bytes = "video", 32 * 1024 * 1024
        else:
            flash("Choose a JPG, PNG or WEBP photo, or an MP4, MOV or WEBM video.", "error")
            return redirect(url_for("community_view", slug=slug))
        media_file.stream.seek(0, os.SEEK_END)
        file_size = media_file.stream.tell()
        media_file.stream.seek(0)
        if not file_size or file_size > max_bytes:
            flash("Community photos must be up to 10 MB and videos up to 32 MB.", "error")
            return redirect(url_for("community_view", slug=slug))
        try:
            media_url = upload_post_media_to_cloudinary(media_file.stream, media_type)
        except Exception as exc:
            app.logger.exception("Community media upload failed")
            flash(str(exc) if isinstance(exc, RuntimeError) else "Media upload failed. Check Cloudinary settings.", "error")
            return redirect(url_for("community_view", slug=slug))
    if not body and not media_url:
        flash("Write a discussion or attach a photo/video.", "error")
        return redirect(url_for("community_view", slug=slug))
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if not role:
            abort(403)
        announcement = bool(request.form.get("announcement")) and community_staff(role)
        c.execute("""INSERT INTO gw_community_posts(community_id,user_id,body,media_url,media_type,is_announcement)
            VALUES(%s,%s,%s,%s,%s,%s)""",
            (community["id"], session["user_id"], body, media_url, media_type, announcement))
        flash("Your community post has been published.", "success")
    return redirect(url_for("community_view", slug=slug))

@app.post("/community/<slug>/posts/<int:post_id>/delete")
@required
def community_delete_post(slug, post_id):
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        post = c.execute("SELECT user_id FROM gw_community_posts WHERE id=%s AND community_id=%s", (post_id, community["id"])).fetchone()
        if not post:
            abort(404)
        if post["user_id"] != session["user_id"] and not community_staff(role):
            abort(403)
        c.execute("DELETE FROM gw_community_posts WHERE id=%s", (post_id,))
        flash("Community post removed.", "success")
    return redirect(url_for("community_view", slug=slug))

@app.post("/community/<slug>/posts/<int:post_id>/report")
@required
def community_report_post(slug, post_id):
    reason = request.form.get("reason", "other").strip().lower()
    if reason not in {"spam", "harassment", "hate", "unsafe", "copyright", "other"}:
        reason = "other"
    details = request.form.get("details", "").strip()[:700]
    with db() as c:
        community = get_community_or_404(c, slug)
        post = c.execute("SELECT id FROM gw_community_posts WHERE id=%s AND community_id=%s", (post_id, community["id"])).fetchone()
        if not post:
            abort(404)
        c.execute("""INSERT INTO gw_community_reports(community_id,post_id,reporter_id,reason,details)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(post_id,reporter_id) DO NOTHING""",
            (community["id"], post_id, session["user_id"], reason, details))
        flash("Your report has been sent to the community moderation team.", "success")
    return redirect(url_for("community_view", slug=slug))

@app.route("/community/<slug>/settings", methods=["GET", "POST"])
@required
def community_settings(slug):
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if role not in {"owner", "admin"}:
            abort(403)
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "General").strip()
            visibility = request.form.get("visibility", "public").strip().lower()
            rules = request.form.get("rules", "").strip()[:3000]
            if not (3 <= len(name) <= 70) or len(description) > 600 or category not in COMMUNITY_CATEGORIES or visibility not in {"public", "private"}:
                flash("Please check the community settings and try again.", "error")
            else:
                c.execute("UPDATE gw_communities SET name=%s,description=%s,category=%s,visibility=%s,rules=%s,updated_at=NOW() WHERE id=%s",
                    (name, description, category, visibility, rules, community["id"]))
                flash("Community settings saved.", "success")
                return redirect(url_for("community_view", slug=slug))
        community = get_community_or_404(c, slug)
        members = c.execute("""SELECT u.id,u.username,u.display_name,m.role,m.joined_at FROM gw_community_members m
            JOIN gw_users u ON u.id=m.user_id WHERE m.community_id=%s
            ORDER BY CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 WHEN 'moderator' THEN 2 ELSE 3 END,m.joined_at""", (community["id"],)).fetchall()
        requests = c.execute("""SELECT r.id,r.message,r.created_at,u.username,u.display_name FROM gw_community_requests r
            JOIN gw_users u ON u.id=r.user_id WHERE r.community_id=%s AND r.status='pending' ORDER BY r.created_at""", (community["id"],)).fetchall()
        reports = c.execute("""SELECT r.id,r.reason,r.details,r.created_at,p.body,u.username AS reporter_username
            FROM gw_community_reports r JOIN gw_community_posts p ON p.id=r.post_id
            JOIN gw_users u ON u.id=r.reporter_id WHERE r.community_id=%s AND r.status='open'
            ORDER BY r.created_at ASC LIMIT 40""", (community["id"],)).fetchall()
    return render_template("community_settings.html", community=community, categories=COMMUNITY_CATEGORIES, members=members, requests=requests, reports=reports, role=role)

@app.post("/community/<slug>/requests/<int:request_id>")
@required
def community_review_request(slug, request_id):
    action = request.form.get("action", "").strip().lower()
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if not community_staff(role):
            abort(403)
        req = c.execute("SELECT * FROM gw_community_requests WHERE id=%s AND community_id=%s AND status='pending'", (request_id, community["id"])).fetchone()
        if not req:
            flash("That request is no longer pending.", "info")
        elif action == "approve":
            c.execute("INSERT INTO gw_community_members(community_id,user_id,role) VALUES(%s,%s,'member') ON CONFLICT DO NOTHING", (community["id"], req["user_id"]))
            c.execute("UPDATE gw_community_requests SET status='approved',reviewed_at=NOW(),reviewed_by=%s WHERE id=%s", (session["user_id"], request_id))
            create_notification(c, req["user_id"], session["user_id"], "community_approved", "community", community["id"], "approved your request to join")
            flash("Membership request approved.", "success")
        elif action == "reject":
            c.execute("UPDATE gw_community_requests SET status='rejected',reviewed_at=NOW(),reviewed_by=%s WHERE id=%s", (session["user_id"], request_id))
            flash("Membership request declined.", "success")
        else:
            flash("Choose approve or reject.", "error")
    return redirect(url_for("community_settings", slug=slug))

@app.post("/community/<slug>/members/<int:member_id>")
@required
def community_member_action(slug, member_id):
    action = request.form.get("action", "").strip().lower()
    with db() as c:
        community = get_community_or_404(c, slug)
        actor_role = community_member_role(c, community["id"], session["user_id"])
        target = c.execute("SELECT role FROM gw_community_members WHERE community_id=%s AND user_id=%s", (community["id"], member_id)).fetchone()
        if not target or member_id == community["created_by"]:
            flash("That member's role cannot be changed here.", "error")
        elif actor_role not in {"owner", "admin", "moderator"}:
            abort(403)
        elif target["role"] in {"owner", "admin"} and actor_role != "owner":
            abort(403)
        elif action == "remove":
            c.execute("DELETE FROM gw_community_members WHERE community_id=%s AND user_id=%s", (community["id"], member_id))
            flash("Member removed from the community.", "success")
        elif action in {"member", "moderator", "admin"}:
            if action == "admin" and actor_role != "owner":
                abort(403)
            if action == "moderator" and actor_role not in {"owner", "admin"}:
                abort(403)
            c.execute("UPDATE gw_community_members SET role=%s WHERE community_id=%s AND user_id=%s", (action, community["id"], member_id))
            flash("Community role updated.", "success")
        else:
            flash("Choose a valid member action.", "error")
    return redirect(url_for("community_settings", slug=slug))

@app.post("/community/<slug>/reports/<int:report_id>")
@required
def community_resolve_report(slug, report_id):
    action = request.form.get("action", "dismiss").strip().lower()
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if not community_staff(role):
            abort(403)
        report = c.execute("SELECT * FROM gw_community_reports WHERE id=%s AND community_id=%s AND status='open'", (report_id, community["id"])).fetchone()
        if not report:
            flash("This report is no longer open.", "info")
        elif action == "remove_post":
            c.execute("DELETE FROM gw_community_posts WHERE id=%s AND community_id=%s", (report["post_id"], community["id"]))
            flash("Reported discussion removed.", "success")
        else:
            c.execute("UPDATE gw_community_reports SET status='dismissed' WHERE id=%s", (report_id,))
            flash("Community report dismissed.", "success")
    return redirect(url_for("community_settings", slug=slug))

@app.post("/community/<slug>/events")
@required
def community_create_event(slug):
    title = request.form.get("title", "").strip()
    details = request.form.get("details", "").strip()[:1000]
    location = request.form.get("location", "").strip()[:180]
    starts_raw = request.form.get("starts_at", "").strip()
    with db() as c:
        community = get_community_or_404(c, slug)
        role = community_member_role(c, community["id"], session["user_id"])
        if not community_staff(role):
            abort(403)
        try:
            starts_at = datetime.fromisoformat(starts_raw)
            if starts_at.tzinfo is None:
                starts_at = starts_at.replace(tzinfo=timezone.utc)
            if starts_at <= datetime.now(timezone.utc):
                raise ValueError("Event must be in the future")
            if not title or len(title) > 100:
                raise ValueError("Invalid title")
        except ValueError:
            flash("Enter a valid event title and a future date/time.", "error")
        else:
            c.execute("INSERT INTO gw_community_events(community_id,creator_id,title,details,starts_at,location) VALUES(%s,%s,%s,%s,%s,%s)",
                (community["id"], session["user_id"], title, details, starts_at, location))
            flash("Community event created.", "success")
    return redirect(url_for("community_view", slug=slug))

@app.route("/explore")
def explore():
    uid = session.get("user_id", -1)
    with db() as c:
        topics = c.execute("""SELECT lower(m.match[1]) AS slug, COUNT(*) AS uses
            FROM gw_posts p CROSS JOIN LATERAL regexp_matches(COALESCE(p.body,''), '#([A-Za-z0-9_]{2,30})', 'g') AS m(match)
            WHERE p.created_at > NOW() - INTERVAL '30 days'
            GROUP BY lower(m.match[1]) ORDER BY uses DESC, slug ASC LIMIT 16""").fetchall()
        people = c.execute("""SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset,
            (SELECT COUNT(*) FROM gw_follows f WHERE f.followed_id=u.id) AS followers
            FROM gw_users u WHERE u.is_verified=TRUE AND u.is_suspended=FALSE AND u.id<>%s
              AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
                (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
              AND NOT EXISTS(SELECT 1 FROM gw_follows f WHERE f.follower_id=%s AND f.followed_id=u.id)
            ORDER BY followers DESC,u.created_at DESC LIMIT 8""", (uid,uid,uid,uid)).fetchall()
        communities = c.execute("""SELECT co.id,co.name,co.slug,co.description,co.category,co.visibility,
            (SELECT COUNT(*) FROM gw_community_members cm WHERE cm.community_id=co.id) AS members
            FROM gw_communities co WHERE co.visibility='public'
            ORDER BY members DESC,co.created_at DESC LIMIT 8""").fetchall()
        posts = c.execute("""SELECT p.id,p.body,p.media_url,p.media_type,p.created_at,
            u.username,u.display_name,u.avatar_url,u.avatar_preset,
            (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
            (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments
            FROM gw_posts p JOIN gw_users u ON u.id=p.user_id
            WHERE u.is_suspended=FALSE AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
              (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
            ORDER BY likes DESC,p.created_at DESC LIMIT 12""", (uid,uid)).fetchall()
    return render_template("explore.html", topics=topics, people=people, communities=communities, posts=posts)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()[:80]
    uid = session.get("user_id", -1)
    people, posts, communities = [], [], []
    if len(q) >= 2:
        pattern = f"%{q}%"
        with db() as c:
            people = c.execute("""SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset
                FROM gw_users u WHERE u.is_verified=TRUE AND u.is_suspended=FALSE
                  AND (u.username ILIKE %s OR u.display_name ILIKE %s)
                  AND u.id<>%s AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
                    (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
                ORDER BY u.created_at DESC LIMIT 20""", (pattern,pattern,uid,uid,uid)).fetchall()
            posts = c.execute("""SELECT p.id,p.body,p.media_url,p.media_type,p.created_at,
                u.username,u.display_name,u.avatar_url,u.avatar_preset,
                (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
                (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments
                FROM gw_posts p JOIN gw_users u ON u.id=p.user_id
                WHERE p.body ILIKE %s AND u.is_suspended=FALSE AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
                  (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
                ORDER BY p.created_at DESC LIMIT 30""", (pattern,uid,uid)).fetchall()
            communities = c.execute("""SELECT co.id,co.name,co.slug,co.description,co.category,co.visibility,
                (SELECT COUNT(*) FROM gw_community_members cm WHERE cm.community_id=co.id) AS members
                FROM gw_communities co WHERE (co.name ILIKE %s OR co.slug ILIKE %s OR co.description ILIKE %s)
                  AND (co.visibility='public' OR EXISTS(SELECT 1 FROM gw_community_members mine WHERE mine.community_id=co.id AND mine.user_id=%s))
                ORDER BY members DESC LIMIT 20""", (pattern,pattern,pattern,uid)).fetchall()
    return render_template("search.html", q=q, people=people, posts=posts, communities=communities)


@app.route("/topics/<slug>")
def topic_detail(slug):
    slug = (slug or "").lower()
    if not re.fullmatch(r"[a-z0-9_]{2,30}", slug):
        abort(404)
    uid = session.get("user_id", -1)
    pattern = r"(^|[^[:alnum:]_])#" + slug + r"([^[:alnum:]_]|$)"
    with db() as c:
        posts = c.execute("""SELECT p.id,p.body,p.media_url,p.media_type,p.created_at,
            u.username,u.display_name,u.avatar_url,u.avatar_preset,
            (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
            (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments
            FROM gw_posts p JOIN gw_users u ON u.id=p.user_id
            WHERE p.body ~* %s AND u.is_suspended=FALSE AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
              (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
            ORDER BY p.created_at DESC LIMIT 60""", (pattern,uid,uid)).fetchall()
    return render_template("topic.html", slug=slug, posts=posts)


@app.route("/messages")
@required
def messages_inbox():
    uid = session["user_id"]
    with db() as c:
        conversations = c.execute("""SELECT conv.id,conv.title,conv.is_group,conv.updated_at,
            (SELECT string_agg(u.display_name, ', ' ORDER BY u.display_name)
             FROM gw_conversation_members other_cm JOIN gw_users u ON u.id=other_cm.user_id
             WHERE other_cm.conversation_id=conv.id AND other_cm.user_id<>%s) AS participant_names,
            (SELECT u.username FROM gw_conversation_members other_cm JOIN gw_users u ON u.id=other_cm.user_id
             WHERE other_cm.conversation_id=conv.id AND other_cm.user_id<>%s ORDER BY other_cm.joined_at LIMIT 1) AS other_username,
            (SELECT m.body FROM gw_messages m WHERE m.conversation_id=conv.id AND m.deleted_at IS NULL
             ORDER BY m.created_at DESC LIMIT 1) AS last_message,
            (SELECT COUNT(*) FROM gw_messages m JOIN gw_conversation_members mine
             ON mine.conversation_id=m.conversation_id AND mine.user_id=%s
             WHERE m.conversation_id=conv.id AND m.sender_id<>%s AND m.deleted_at IS NULL
               AND (mine.last_read_at IS NULL OR m.created_at>mine.last_read_at)) AS unread
            FROM gw_conversations conv JOIN gw_conversation_members mine ON mine.conversation_id=conv.id
            WHERE mine.user_id=%s ORDER BY conv.updated_at DESC LIMIT 100""",
            (uid, uid, uid, uid, uid)).fetchall()
    return render_template("messages.html", conversations=conversations)


@app.route("/messages/new", methods=["GET", "POST"])
@required
def message_new():
    if request.method == "GET":
        preset = request.args.get("to", "").strip().lower()
        return render_template("message_new.html", preset_username=preset)
    if not rate_limit_allowed("message_start", 12, 3600, str(session["user_id"])):
        flash("You are starting conversations too quickly. Please try again later.", "error")
        return redirect(url_for("messages_inbox"))
    raw = request.form.get("usernames", "")
    usernames = []
    for value in raw.split(","):
        name = value.strip().lstrip("@").lower()
        if name and re.fullmatch(r"[a-z0-9_]{3,30}", name) and name not in usernames:
            usernames.append(name)
    title = request.form.get("title", "").strip()[:100]
    if not usernames or len(usernames) > 19:
        flash("Enter between 1 and 19 valid usernames. Separate group members with commas.", "error")
        return render_template("message_new.html", preset_username=raw), 400
    uid = session["user_id"]
    placeholders = ",".join(["%s"] * len(usernames))
    with db() as c:
        recipients = c.execute(f"SELECT id,username FROM gw_users WHERE username IN ({placeholders}) AND is_suspended=FALSE AND is_verified=TRUE", tuple(usernames)).fetchall()
        found = {r["username"]: r for r in recipients}
        missing = [name for name in usernames if name not in found]
        if missing:
            flash("We could not find these active usernames: " + ", ".join(missing), "error")
            return render_template("message_new.html", preset_username=raw), 400
        recipient_ids = [found[name]["id"] for name in usernames]
        if uid in recipient_ids:
            flash("You cannot start a conversation with yourself.", "error")
            return render_template("message_new.html", preset_username=raw), 400
        for rid in recipient_ids:
            blocked = c.execute("SELECT 1 FROM gw_user_blocks WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s) LIMIT 1", (uid, rid, rid, uid)).fetchone()
            if blocked:
                flash("A conversation cannot be started because a block is active between these accounts.", "error")
                return redirect(url_for("messages_inbox"))
        if len(recipient_ids) == 1:
            rid = recipient_ids[0]
            existing = c.execute("""SELECT conv.id FROM gw_conversations conv
                JOIN gw_conversation_members mine ON mine.conversation_id=conv.id AND mine.user_id=%s
                JOIN gw_conversation_members other ON other.conversation_id=conv.id AND other.user_id=%s
                WHERE conv.is_group=FALSE
                  AND (SELECT COUNT(*) FROM gw_conversation_members all_members WHERE all_members.conversation_id=conv.id)=2
                ORDER BY conv.updated_at DESC LIMIT 1""", (uid, rid)).fetchone()
            if existing:
                return redirect(url_for("message_thread", conversation_id=existing["id"]))
        is_group = len(recipient_ids) > 1
        if is_group and not title:
            title = "Gather group conversation"
        conv = c.execute("INSERT INTO gw_conversations(title,is_group,created_by) VALUES(%s,%s,%s) RETURNING id", (title, is_group, uid)).fetchone()
        conversation_id = conv["id"]
        c.execute("INSERT INTO gw_conversation_members(conversation_id,user_id,role) VALUES(%s,%s,'owner')", (conversation_id, uid))
        for rid in recipient_ids:
            c.execute("INSERT INTO gw_conversation_members(conversation_id,user_id) VALUES(%s,%s)", (conversation_id, rid))
        if is_group:
            for rid in recipient_ids:
                create_notification(c, rid, uid, "message_group", "conversation", conversation_id, "added you to a Gather group conversation")
    return redirect(url_for("message_thread", conversation_id=conversation_id))


@app.route("/messages/<int:conversation_id>", methods=["GET"])
@required
def message_thread(conversation_id):
    uid = session["user_id"]
    with db() as c:
        membership = c.execute("""SELECT conv.id,conv.title,conv.is_group,conv.created_by
            FROM gw_conversations conv JOIN gw_conversation_members cm ON cm.conversation_id=conv.id
            WHERE conv.id=%s AND cm.user_id=%s""", (conversation_id, uid)).fetchone()
        if not membership:
            abort(404)
        c.execute("UPDATE gw_conversation_members SET last_read_at=NOW() WHERE conversation_id=%s AND user_id=%s", (conversation_id, uid))
        members = c.execute("""SELECT u.id,u.username,u.display_name,u.avatar_url,u.avatar_preset,cm.role
            FROM gw_conversation_members cm JOIN gw_users u ON u.id=cm.user_id
            WHERE cm.conversation_id=%s ORDER BY cm.joined_at""", (conversation_id,)).fetchall()
        rows = c.execute("""SELECT m.id,m.sender_id,m.body,m.created_at,u.username,u.display_name,u.avatar_url,u.avatar_preset
            FROM gw_messages m JOIN gw_users u ON u.id=m.sender_id
            WHERE m.conversation_id=%s AND m.deleted_at IS NULL
            ORDER BY m.created_at ASC LIMIT 250""", (conversation_id,)).fetchall()
    return render_template("message_thread.html", conversation=membership, members=members, messages=rows)


@app.post("/messages/<int:conversation_id>/send")
@required
def message_send(conversation_id):
    uid = session["user_id"]
    body = request.form.get("body", "").strip()
    if not body or len(body) > 4000:
        flash("Messages must contain 1–4,000 characters.", "error")
        return redirect(url_for("message_thread", conversation_id=conversation_id))
    if not rate_limit_allowed("send_message", 40, 300, str(uid)):
        flash("You are sending messages too quickly. Please slow down.", "error")
        return redirect(url_for("message_thread", conversation_id=conversation_id))
    with db() as c:
        membership = c.execute("""SELECT conv.id,conv.is_group FROM gw_conversations conv
            JOIN gw_conversation_members cm ON cm.conversation_id=conv.id
            WHERE conv.id=%s AND cm.user_id=%s""", (conversation_id, uid)).fetchone()
        if not membership:
            abort(404)
        recipients = c.execute("SELECT user_id FROM gw_conversation_members WHERE conversation_id=%s AND user_id<>%s", (conversation_id, uid)).fetchall()
        if not membership["is_group"]:
            for row in recipients:
                blocked = c.execute("SELECT 1 FROM gw_user_blocks WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s) LIMIT 1", (uid, row["user_id"], row["user_id"], uid)).fetchone()
                if blocked:
                    flash("Messaging is unavailable because a block is active.", "error")
                    return redirect(url_for("messages_inbox"))
        message = c.execute("INSERT INTO gw_messages(conversation_id,sender_id,body) VALUES(%s,%s,%s) RETURNING id", (conversation_id, uid, body)).fetchone()
        c.execute("UPDATE gw_conversations SET updated_at=NOW() WHERE id=%s", (conversation_id,))
        for row in recipients:
            create_notification(c, row["user_id"], uid, "message", "conversation", conversation_id, "sent you a message")
    return redirect(url_for("message_thread", conversation_id=conversation_id) + f"#message-{message['id']}")


@app.post("/messages/<int:conversation_id>/leave")
@required
def message_leave(conversation_id):
    uid = session["user_id"]
    with db() as c:
        membership = c.execute("SELECT is_group FROM gw_conversations conv JOIN gw_conversation_members cm ON cm.conversation_id=conv.id WHERE conv.id=%s AND cm.user_id=%s", (conversation_id, uid)).fetchone()
        if not membership:
            abort(404)
        if not membership["is_group"]:
            flash("Direct conversations cannot be left; you can use the account blocking controls instead.", "info")
        else:
            c.execute("DELETE FROM gw_conversation_members WHERE conversation_id=%s AND user_id=%s", (conversation_id, uid))
            remaining = c.execute("SELECT COUNT(*) AS n FROM gw_conversation_members WHERE conversation_id=%s", (conversation_id,)).fetchone()["n"]
            if remaining == 0:
                c.execute("DELETE FROM gw_conversations WHERE id=%s", (conversation_id,))
            flash("You left the group conversation.", "success")
    return redirect(url_for("messages_inbox"))


@app.route("/feed")
def feed():
    uid = session.get("user_id", -1)
    with db() as c:
        posts = c.execute("""SELECT * FROM (
            SELECT p.id,p.user_id,p.body,p.media_url,p.media_type,p.created_at AS post_created_at,
                   p.created_at AS feed_created_at,u.username,u.display_name,u.avatar_url,u.avatar_preset,
                   (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
                   (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments,
                   EXISTS(SELECT 1 FROM gw_likes l WHERE l.post_id=p.id AND l.user_id=%s) AS liked,
                   EXISTS(SELECT 1 FROM gw_bookmarks b WHERE b.post_id=p.id AND b.user_id=%s) AS bookmarked,
                   FALSE AS is_repost, NULL::VARCHAR(30) AS reposter_username,
                   NULL::VARCHAR(60) AS reposter_display_name
            FROM gw_posts p JOIN gw_users u ON u.id=p.user_id
            WHERE u.is_suspended=FALSE AND NOT EXISTS(
              SELECT 1 FROM gw_user_blocks b WHERE (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s)
            )
            UNION ALL
            SELECT p.id,p.user_id,p.body,p.media_url,p.media_type,p.created_at AS post_created_at,
                   r.created_at AS feed_created_at,u.username,u.display_name,u.avatar_url,u.avatar_preset,
                   (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
                   (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments,
                   EXISTS(SELECT 1 FROM gw_likes l WHERE l.post_id=p.id AND l.user_id=%s) AS liked,
                   EXISTS(SELECT 1 FROM gw_bookmarks b WHERE b.post_id=p.id AND b.user_id=%s) AS bookmarked,
                   TRUE AS is_repost, ru.username AS reposter_username,
                   ru.display_name AS reposter_display_name
            FROM gw_reposts r JOIN gw_posts p ON p.id=r.post_id
            JOIN gw_users u ON u.id=p.user_id JOIN gw_users ru ON ru.id=r.user_id
            WHERE u.is_suspended=FALSE AND ru.is_suspended=FALSE
              AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
              AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE (b.blocker_id=%s AND b.blocked_id=ru.id) OR (b.blocker_id=ru.id AND b.blocked_id=%s))
        ) AS feed_items ORDER BY feed_created_at DESC LIMIT 60""",
        (uid, uid, uid, uid, uid, uid, uid, uid, uid, uid)).fetchall()
    return render_template("feed.html", posts=posts)


@app.route("/moments")
def moments():
    """Full-screen media discovery for both photos and short videos."""
    uid = session.get("user_id", -1)
    with db() as c:
        rows = c.execute("""SELECT p.id,p.body,p.media_url,p.media_type,p.created_at,
            u.id AS user_id,u.username,u.display_name,u.avatar_url,u.avatar_preset,
            (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
            (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments,
            (SELECT COUNT(*) FROM gw_reposts rp WHERE rp.post_id=p.id) AS reposts,
            EXISTS(SELECT 1 FROM gw_likes l WHERE l.post_id=p.id AND l.user_id=%s) AS liked,
            EXISTS(SELECT 1 FROM gw_bookmarks b WHERE b.post_id=p.id AND b.user_id=%s) AS bookmarked,
            EXISTS(SELECT 1 FROM gw_follows f WHERE f.follower_id=%s AND f.followed_id=u.id) AS following
            FROM gw_posts p JOIN gw_users u ON u.id=p.user_id
            WHERE p.media_type IN ('image','video') AND p.media_url IS NOT NULL AND u.is_suspended=FALSE
              AND NOT EXISTS(SELECT 1 FROM gw_user_blocks b WHERE
                (b.blocker_id=%s AND b.blocked_id=u.id) OR (b.blocker_id=u.id AND b.blocked_id=%s))
            ORDER BY p.created_at DESC LIMIT 80""", (uid, uid, uid, uid, uid)).fetchall()
    return render_template("moments.html", moments=rows)


@app.route("/notifications")
@required
def notifications():
    uid = session["user_id"]
    with db() as c:
        rows = c.execute("""SELECT n.id,n.notification_type,n.entity_type,n.entity_id,n.message,n.is_read,n.created_at,
            u.username AS actor_username,u.display_name AS actor_display_name,u.avatar_url AS actor_avatar_url,
            u.avatar_preset AS actor_avatar_preset
            FROM gw_notifications n LEFT JOIN gw_users u ON u.id=n.actor_id
            WHERE n.recipient_id=%s ORDER BY n.created_at DESC LIMIT 100""", (uid,)).fetchall()
    return render_template("notifications.html", notifications=rows)


@app.post("/notifications/<int:notification_id>/read")
@required
def mark_notification_read(notification_id):
    with db() as c:
        c.execute("UPDATE gw_notifications SET is_read=TRUE WHERE id=%s AND recipient_id=%s", (notification_id, session["user_id"]))
    return redirect(request.referrer or url_for("notifications"))


@app.post("/notifications/read-all")
@required
def mark_all_notifications_read():
    with db() as c:
        c.execute("UPDATE gw_notifications SET is_read=TRUE WHERE recipient_id=%s AND is_read=FALSE", (session["user_id"],))
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications"))


@app.route("/saved")
@required
def saved_posts():
    uid = session["user_id"]
    with db() as c:
        posts = c.execute("""SELECT p.id,p.user_id,p.body,p.media_url,p.media_type,p.created_at,
            u.username,u.display_name,u.avatar_url,u.avatar_preset,
            (SELECT COUNT(*) FROM gw_likes l WHERE l.post_id=p.id) AS likes,
            (SELECT COUNT(*) FROM gw_comments cm WHERE cm.post_id=p.id) AS comments,
            EXISTS(SELECT 1 FROM gw_likes l WHERE l.post_id=p.id AND l.user_id=%s) AS liked,
            TRUE AS bookmarked
            FROM gw_bookmarks b JOIN gw_posts p ON p.id=b.post_id JOIN gw_users u ON u.id=p.user_id
            WHERE b.user_id=%s AND u.is_suspended=FALSE
              AND NOT EXISTS(SELECT 1 FROM gw_user_blocks x WHERE (x.blocker_id=%s AND x.blocked_id=u.id) OR (x.blocker_id=u.id AND x.blocked_id=%s))
            ORDER BY b.created_at DESC LIMIT 100""", (uid, uid, uid, uid)).fetchall()
    return render_template("saved.html", posts=posts)

@app.post("/posts")
@required
def create_post():
    return_target = url_for("moments") if request.form.get("return_to") == "moments" else url_for("feed")
    if not rate_limit_allowed("create_post", 30, 3600, str(session.get("user_id"))):
        flash("You are posting too quickly. Please try again later.", "error")
        return redirect(return_target)

    body = request.form.get("body", "").strip()
    media_url = request.form.get("media_url", "").strip()
    media_type = request.form.get("media_type", "").strip()
    media_file = next((item for item in request.files.getlist("media_file") if item and item.filename), None)

    if len(body) > 2000:
        flash("Your caption must be 2,000 characters or fewer.", "error")
        return redirect(return_target)

    # A user may upload a file OR paste an existing HTTPS media URL, not both.
    if media_file and media_file.filename:
        if media_url:
            flash("Choose a file upload or an external media URL, not both.", "error")
            return redirect(return_target)

        filename = media_file.filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        image_types = {
            "jpg": ("image/jpeg",), "jpeg": ("image/jpeg",),
            "png": ("image/png",), "webp": ("image/webp",),
        }
        video_types = {
            "mp4": ("video/mp4", "application/mp4"),
            "m4v": ("video/x-m4v", "video/mp4"),
            "mov": ("video/quicktime",),
            "webm": ("video/webm",),
        }
        mimetype = (media_file.mimetype or "").lower()
        if extension in image_types and (mimetype in image_types[extension] or mimetype == "application/octet-stream"):
            media_type = "image"
            max_bytes = 10 * 1024 * 1024
        elif extension in video_types and (mimetype in video_types[extension] or mimetype == "application/octet-stream" or (extension == "m4v" and mimetype == "video/x-m4v")):
            media_type = "video"
            max_bytes = 32 * 1024 * 1024
        else:
            flash("Supported uploads: JPG, PNG or WEBP photos; MP4, MOV or WEBM videos.", "error")
            return redirect(return_target)

        media_file.stream.seek(0, os.SEEK_END)
        file_size = media_file.stream.tell()
        media_file.stream.seek(0)
        if file_size <= 0:
            flash("The selected file is empty. Choose another file.", "error")
            return redirect(return_target)
        if file_size > max_bytes:
            limit = "10 MB" if media_type == "image" else "32 MB"
            flash(f"Your {media_type} must be {limit} or smaller.", "error")
            return redirect(return_target)
        try:
            media_url = upload_post_media_to_cloudinary(media_file.stream, media_type)
        except Exception as exc:
            app.logger.exception("Gather World post media upload failed")
            flash(str(exc) if isinstance(exc, RuntimeError) else "The media upload failed. Check your Cloudinary settings and try again.", "error")
            return redirect(return_target)

    elif media_url:
        if not media_url.startswith("https://") or media_type not in ("image", "video"):
            flash("Use a secure HTTPS image/video URL and select its type.", "error")
            return redirect(return_target)
    else:
        media_url = None
        media_type = None

    if not body and not media_url:
        flash("Write a caption or choose a photo/video to publish.", "error")
        return redirect(return_target)

    with db() as c:
        c.execute(
            "INSERT INTO gw_posts(user_id,body,media_url,media_type) VALUES(%s,%s,%s,%s)",
            (session["user_id"], body, media_url, media_type),
        )
    flash("Your moment has been shared!", "success")
    return redirect(return_target)


@app.errorhandler(413)
def uploaded_file_too_large(_error):
    flash("The upload is too large. Photos can be up to 10 MB and videos up to 32 MB.", "error")
    return redirect(request.referrer or url_for("feed"), code=303)
@app.post("/posts/<int:pid>/delete")
@required
def delete_post(pid):
    with db() as c:c.execute("DELETE FROM gw_posts WHERE id=%s AND user_id=%s",(pid,session["user_id"]))
    return redirect(request.referrer or url_for("feed"))
@app.post("/posts/<int:pid>/like")
@required
def like(pid):
    with db() as c:
        post = c.execute("SELECT user_id FROM gw_posts WHERE id=%s", (pid,)).fetchone()
        if not post:
            flash("This post is no longer available.", "error")
        else:
            existing = c.execute("SELECT 1 FROM gw_likes WHERE user_id=%s AND post_id=%s", (session["user_id"], pid)).fetchone()
            if existing:
                c.execute("DELETE FROM gw_likes WHERE user_id=%s AND post_id=%s", (session["user_id"], pid))
            else:
                c.execute("INSERT INTO gw_likes(user_id,post_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (session["user_id"], pid))
                create_notification(c, post["user_id"], session["user_id"], "like", "post", pid, "liked your post")
    return redirect(request.referrer or url_for("feed"))


@app.post("/posts/<int:pid>/bookmark")
@required
def toggle_bookmark(pid):
    with db() as c:
        exists_post = c.execute("SELECT 1 FROM gw_posts WHERE id=%s", (pid,)).fetchone()
        if not exists_post:
            flash("This post is no longer available.", "error")
        else:
            saved = c.execute("SELECT 1 FROM gw_bookmarks WHERE user_id=%s AND post_id=%s", (session["user_id"], pid)).fetchone()
            if saved:
                c.execute("DELETE FROM gw_bookmarks WHERE user_id=%s AND post_id=%s", (session["user_id"], pid))
                flash("Post removed from Saved.", "info")
            else:
                c.execute("INSERT INTO gw_bookmarks(user_id,post_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (session["user_id"], pid))
                flash("Post saved to your collection.", "success")
    return redirect(request.referrer or url_for("saved_posts"))


@app.post("/posts/<int:pid>/repost")
@required
def repost(pid):
    with db() as c:
        post = c.execute("SELECT user_id FROM gw_posts WHERE id=%s", (pid,)).fetchone()
        if not post:
            flash("This post is no longer available.", "error")
        elif post["user_id"] == session["user_id"]:
            flash("You cannot repost your own post.", "info")
        else:
            inserted = c.execute("INSERT INTO gw_reposts(user_id,post_id) VALUES(%s,%s) ON CONFLICT(user_id,post_id) DO NOTHING RETURNING id", (session["user_id"], pid)).fetchone()
            if inserted:
                create_notification(c, post["user_id"], session["user_id"], "repost", "post", pid, "reposted your post")
                flash("Post shared with your followers.", "success")
            else:
                flash("You have already reposted this post.", "info")
    return redirect(request.referrer or url_for("feed"))


@app.post("/posts/<int:pid>/comment")
@required
def comment(pid):
    if not rate_limit_allowed("comment", 40, 3600, str(session.get("user_id"))):
        flash("You are commenting too quickly. Please try again later.", "error")
        return redirect(url_for("post_detail", pid=pid))
    body = request.form.get("body", "").strip()
    parent_raw = request.form.get("parent_comment_id", "").strip()
    parent_id = None
    if parent_raw:
        if not parent_raw.isdigit():
            flash("Invalid reply target.", "error")
            return redirect(url_for("post_detail", pid=pid))
        parent_id = int(parent_raw)
    if not body or len(body) > 1000:
        flash("Write a comment of up to 1,000 characters.", "error")
    else:
        with db() as c:
            post = c.execute("SELECT user_id FROM gw_posts WHERE id=%s", (pid,)).fetchone()
            parent = None
            if parent_id:
                parent = c.execute("SELECT id,user_id,post_id FROM gw_comments WHERE id=%s", (parent_id,)).fetchone()
                if not parent or parent["post_id"] != pid:
                    flash("That comment is no longer available.", "error")
                    return redirect(url_for("post_detail", pid=pid))
            if post:
                inserted = c.execute("INSERT INTO gw_comments(post_id,user_id,body,parent_comment_id) VALUES(%s,%s,%s,%s) RETURNING id", (pid,session["user_id"],body,parent_id)).fetchone()
                if parent_id and parent:
                    create_notification(c, parent["user_id"], session["user_id"], "reply", "post", pid, "replied to your comment")
                else:
                    create_notification(c, post["user_id"], session["user_id"], "comment", "post", pid, "commented on your post")
    return redirect(url_for("post_detail", pid=pid))

@app.route("/posts/<int:pid>")
def post_detail(pid):
    viewer_id = session.get("user_id", -1)
    with db() as c:
        p = c.execute("""SELECT p.*,u.username,u.display_name,u.avatar_url,u.avatar_preset,
            (SELECT COUNT(*) FROM gw_likes WHERE post_id=p.id) AS likes,
            EXISTS(SELECT 1 FROM gw_likes WHERE post_id=p.id AND user_id=%s) AS liked,
            EXISTS(SELECT 1 FROM gw_bookmarks WHERE post_id=p.id AND user_id=%s) AS bookmarked
            FROM gw_posts p JOIN gw_users u ON u.id=p.user_id
            WHERE p.id=%s AND u.is_suspended=FALSE""", (viewer_id, viewer_id, pid)).fetchone()
        if not p:
            return render_template("404.html"), 404
        all_comments = c.execute("""SELECT c.id,c.parent_comment_id,c.body,c.created_at,u.id AS author_id,
            u.username,u.display_name,u.avatar_url,u.avatar_preset
            FROM gw_comments c JOIN gw_users u ON u.id=c.user_id
            WHERE c.post_id=%s AND u.is_suspended=FALSE ORDER BY c.created_at ASC""", (pid,)).fetchall()
    top_comments = [x for x in all_comments if not x["parent_comment_id"]]
    replies_by_comment = {}
    for item in all_comments:
        if item["parent_comment_id"]:
            replies_by_comment.setdefault(item["parent_comment_id"], []).append(item)
    return render_template("post.html", p=p, comments=top_comments, replies_by_comment=replies_by_comment)

@app.post("/u/<username>/follow")
@required
def follow(username):
    with db() as c:
        target = c.execute("SELECT id,is_suspended FROM gw_users WHERE username=%s", (username.lower(),)).fetchone()
        if target and not target["is_suspended"] and target["id"] != session["user_id"] and not c.execute(
            "SELECT 1 FROM gw_user_blocks WHERE (blocker_id=%s AND blocked_id=%s) OR (blocker_id=%s AND blocked_id=%s)",
            (session["user_id"], target["id"], target["id"], session["user_id"])
        ).fetchone():
            existing = c.execute("SELECT 1 FROM gw_follows WHERE follower_id=%s AND followed_id=%s", (session["user_id"], target["id"])).fetchone()
            if existing:
                c.execute("DELETE FROM gw_follows WHERE follower_id=%s AND followed_id=%s", (session["user_id"], target["id"]))
            else:
                c.execute("INSERT INTO gw_follows(follower_id,followed_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (session["user_id"], target["id"]))
                create_notification(c, target["id"], session["user_id"], "follow", "user", session["user_id"], "started following you")
    if request.form.get("return_to") == "moments":
        return redirect(url_for("moments"))
    return redirect(url_for("public_profile", username=username))

@app.route("/u/<username>/followers")
@app.route("/u/<username>/following")
def connection_list(username):
    followers=request.path.endswith("/followers")
    col="follower_id" if followers else "followed_id";other="followed_id" if followers else "follower_id"
    with db() as c:rows=c.execute(f"SELECT u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset FROM gw_follows f JOIN gw_users u ON u.id=f.{other} WHERE f.{col}=(SELECT id FROM gw_users WHERE username=%s) ORDER BY f.created_at DESC",(username.lower(),)).fetchall()
    return render_template("members.html",rows=rows,q="")
@app.post("/u/<username>/block")
@required
def toggle_block(username):
    target_username = username.lower()
    with db() as c:
        target = c.execute("SELECT id FROM gw_users WHERE username=%s AND is_suspended=FALSE", (target_username,)).fetchone()
        if target and target["id"] != session["user_id"]:
            exists = c.execute("SELECT 1 FROM gw_user_blocks WHERE blocker_id=%s AND blocked_id=%s", (session["user_id"], target["id"])).fetchone()
            if exists:
                c.execute("DELETE FROM gw_user_blocks WHERE blocker_id=%s AND blocked_id=%s", (session["user_id"], target["id"]))
                flash("Member unblocked.", "success")
            else:
                c.execute("INSERT INTO gw_user_blocks(blocker_id,blocked_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (session["user_id"], target["id"]))
                c.execute("DELETE FROM gw_follows WHERE (follower_id=%s AND followed_id=%s) OR (follower_id=%s AND followed_id=%s)", (session["user_id"], target["id"], target["id"], session["user_id"]))
                flash("Member blocked. Their posts will be hidden from you.", "success")
    return redirect(url_for("members"))

@app.route("/blocked")
@required
def blocked_members():
    with db() as c:
        rows = c.execute("""SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset
            FROM gw_user_blocks b JOIN gw_users u ON u.id=b.blocked_id
            WHERE b.blocker_id=%s ORDER BY b.created_at DESC""", (session["user_id"],)).fetchall()
    return render_template("blocked.html", rows=rows)

@app.post("/report/post/<int:pid>")
@required
def report_post(pid):
    if not rate_limit_allowed("report", 15, 86400, str(session.get("user_id"))):
        flash("You have reached the daily report limit.", "error")
        return redirect(request.referrer or url_for("feed"))
    reason = request.form.get("reason", "other").strip().lower()
    details = request.form.get("details", "").strip()[:1000]
    if reason not in {"spam", "harassment", "hate", "unsafe", "copyright", "other"}:
        reason = "other"
    with db() as c:
        post = c.execute("SELECT id,user_id FROM gw_posts WHERE id=%s", (pid,)).fetchone()
        if not post:
            flash("That post is no longer available.", "error")
        elif post["user_id"] == session["user_id"]:
            flash("You cannot report your own post.", "info")
        else:
            already = c.execute("SELECT 1 FROM gw_reports WHERE reporter_id=%s AND content_type='post' AND content_id=%s AND status='open'", (session["user_id"], pid)).fetchone()
            if already:
                flash("You have already reported this post.", "info")
            else:
                c.execute("INSERT INTO gw_reports(reporter_id,content_type,content_id,reason,details) VALUES(%s,'post',%s,%s,%s)", (session["user_id"], pid, reason, details))
                flash("Thank you. Your report has been sent to the moderation team.", "success")
    return redirect(request.referrer or url_for("feed"))

@app.post("/report/user/<username>")
@required
def report_user(username):
    if not rate_limit_allowed("report", 15, 86400, str(session.get("user_id"))):
        flash("You have reached the daily report limit.", "error")
        return redirect(request.referrer or url_for("members"))
    reason = request.form.get("reason", "other").strip().lower()
    details = request.form.get("details", "").strip()[:1000]
    if reason not in {"spam", "harassment", "hate", "impersonation", "unsafe", "other"}:
        reason = "other"
    with db() as c:
        target = c.execute("SELECT id FROM gw_users WHERE username=%s AND is_suspended=FALSE", (username.lower(),)).fetchone()
        if not target or target["id"] == session["user_id"]:
            flash("This member cannot be reported.", "error")
        else:
            already = c.execute("SELECT 1 FROM gw_reports WHERE reporter_id=%s AND content_type='user' AND content_id=%s AND status='open'", (session["user_id"], target["id"])).fetchone()
            if already:
                flash("You have already reported this member.", "info")
            else:
                c.execute("INSERT INTO gw_reports(reporter_id,content_type,content_id,reason,details) VALUES(%s,'user',%s,%s,%s)", (session["user_id"], target["id"], reason, details))
                flash("Thank you. Your report has been sent to the moderation team.", "success")
    return redirect(request.referrer or url_for("members"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    with db() as c:
        stats = c.execute("""SELECT (SELECT COUNT(*) FROM gw_users) users,
            (SELECT COUNT(*) FROM gw_users WHERE is_suspended=TRUE) suspended,
            (SELECT COUNT(*) FROM gw_posts) posts,
            (SELECT COUNT(*) FROM gw_reports WHERE status='open') open_reports""").fetchone()
        users = c.execute("SELECT id,username,email,display_name,is_verified,is_suspended,created_at FROM gw_users ORDER BY created_at DESC LIMIT 50").fetchall()
        reports = c.execute("""SELECT r.*,u.username reporter_username FROM gw_reports r
            JOIN gw_users u ON u.id=r.reporter_id WHERE r.status='open' ORDER BY r.created_at ASC LIMIT 50""").fetchall()
    return render_template("admin.html", stats=stats, users=users, reports=reports)

@app.post("/admin/reports/<int:report_id>/resolve")
@admin_required
def resolve_report(report_id):
    action = request.form.get("action", "dismiss").strip().lower()
    note = request.form.get("note", "").strip()[:500]
    with db() as c:
        report = c.execute("SELECT * FROM gw_reports WHERE id=%s AND status='open'", (report_id,)).fetchone()
        if not report:
            flash("This report is no longer open.", "info")
            return redirect(url_for("admin_dashboard"))
        if action == "remove_post" and report["content_type"] == "post":
            c.execute("DELETE FROM gw_posts WHERE id=%s", (report["content_id"],))
            status = "actioned"
            log_action = "remove_reported_post"
        elif action == "suspend_user":
            if report["content_type"] == "post":
                target = c.execute("SELECT user_id AS id FROM gw_posts WHERE id=%s", (report["content_id"],)).fetchone()
            else:
                target = {"id": report["content_id"]}
            if not target:
                status = "dismissed"
                log_action = "dismiss_missing_target"
            else:
                target_account = c.execute("SELECT username,email FROM gw_users WHERE id=%s", (target["id"],)).fetchone()
                if not target_account or target_account["username"].lower() in ADMIN_USERNAMES or target_account["email"].lower() in ADMIN_EMAILS:
                    flash("Configured administrators cannot be suspended here.", "error")
                    return redirect(url_for("admin_dashboard"))
                c.execute("UPDATE gw_users SET is_suspended=TRUE,suspended_reason=%s,session_version=session_version+1 WHERE id=%s", (note or "Suspended after moderation review.", target["id"]))
                status = "actioned"
                log_action = "suspend_reported_user"
        else:
            status = "dismissed"
            log_action = "dismiss_report"
        c.execute("UPDATE gw_reports SET status=%s,resolved_at=NOW(),resolved_by=%s WHERE id=%s", (status, session["user_id"], report_id))
        c.execute("INSERT INTO gw_admin_actions(admin_id,action,target_type,target_id,note) VALUES(%s,%s,%s,%s,%s)", (session["user_id"], log_action, report["content_type"], report["content_id"], note))
    flash("Moderation action recorded.", "success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/users/<int:user_id>/status")
@admin_required
def admin_user_status(user_id):
    action = request.form.get("action", "").strip().lower()
    note = request.form.get("note", "").strip()[:500]
    with db() as c:
        target = c.execute("SELECT id,username,email FROM gw_users WHERE id=%s", (user_id,)).fetchone()
        if not target:
            flash("User not found.", "error")
        elif target["username"].lower() in ADMIN_USERNAMES or target["email"].lower() in ADMIN_EMAILS:
            flash("Configured administrators cannot be suspended from this screen.", "error")
        elif action == "suspend":
            c.execute("UPDATE gw_users SET is_suspended=TRUE,suspended_reason=%s,session_version=session_version+1 WHERE id=%s", (note or "Suspended by an administrator.", user_id))
            c.execute("INSERT INTO gw_admin_actions(admin_id,action,target_type,target_id,note) VALUES(%s,'suspend_user','user',%s,%s)", (session["user_id"], user_id, note))
            flash("User suspended. Existing sessions have been invalidated.", "success")
        elif action == "restore":
            c.execute("UPDATE gw_users SET is_suspended=FALSE,suspended_reason=NULL,session_version=session_version+1 WHERE id=%s", (user_id,))
            c.execute("INSERT INTO gw_admin_actions(admin_id,action,target_type,target_id,note) VALUES(%s,'restore_user','user',%s,%s)", (session["user_id"], user_id, note))
            flash("User account restored.", "success")
        else:
            flash("Choose a valid user action.", "error")
    return redirect(url_for("admin_dashboard"))

# -----------------------------------------------------------------------------
# PHASE 7 — GATHER AI
# -----------------------------------------------------------------------------
def gemini_generate_reply(history):
    """Call Gemini server-side, with bounded retry and graceful timeout handling."""
    if not GEMINI_API_KEY:
        raise RuntimeError("Gather AI is not connected yet. Add GEMINI_API_KEY to your private .env and restart Flask.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,100}", GEMINI_MODEL):
        raise RuntimeError("GEMINI_MODEL contains unsupported characters. Check your private .env.")

    # Keep the key out of the URL and browser-facing logs.
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(GEMINI_MODEL, safe="")
        + ":generateContent"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": "You are Gather AI, a helpful assistant inside Gather World. Be clear, respectful, accurate, and concise. Do not claim to have performed actions outside this chat. Protect user privacy and never ask for passwords, API keys, or payment secrets."}]},
        "contents": history,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1200},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
        method="POST",
    )

    data = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            # Retry once only for transient Google service errors.
            if exc.code in (500, 502, 503, 504) and attempt == 0:
                app.logger.warning("Gemini temporary HTTP %s; retrying once after a short delay.", exc.code)
                time.sleep(1.5)
                continue
            app.logger.warning("Gemini request failed with HTTP %s.", exc.code)
            if exc.code in (400, 404):
                raise RuntimeError("Gemini rejected the model or request. Check GEMINI_MODEL in your private .env and confirm that model is available to your API project.") from None
            if exc.code in (401, 403):
                raise RuntimeError("Gemini could not authorize this API key. Check that the key is active and its project has Gemini API access.") from None
            if exc.code == 429:
                raise RuntimeError("Gather AI has reached a Gemini rate or quota limit. Check your Google AI Studio usage and try again later.") from None
            raise RuntimeError("Gemini is temporarily unavailable (HTTP %s). Please try again shortly." % exc.code) from None
        except TimeoutError:
            app.logger.warning("Gemini request timed out after %s seconds.", GEMINI_TIMEOUT_SECONDS)
            raise RuntimeError(
                "Gemini did not respond within %s seconds. This is a network or provider timeout, "
                "not proof that your API key is invalid. Try again with a shorter message or check "
                "your internet connection and Google's service status."
                % GEMINI_TIMEOUT_SECONDS
            ) from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                app.logger.warning("Gemini connection timed out after %s seconds.", GEMINI_TIMEOUT_SECONDS)
                raise RuntimeError(
                    "The connection to Gemini timed out after %s seconds. Check your internet connection and try again."
                    % GEMINI_TIMEOUT_SECONDS
                ) from None
            app.logger.warning("Gemini connection failed: %s", type(getattr(exc, "reason", None)).__name__)
            raise RuntimeError("Gather AI could not connect to Google. Check your internet connection and try again.") from None
    if data is None:
        raise RuntimeError("Gemini is temporarily unavailable. Please try again shortly.")

    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
    reply = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text"))
    if not reply.strip():
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        if block_reason:
            raise RuntimeError("Gemini could not answer this prompt because it was blocked by its safety system. Please rephrase your message.")
        raise RuntimeError("Gemini returned no text for this request. Please try a different message.")
    return reply.strip()[:12000]


@app.route("/ai")
@required
def ai_home():
    with db() as c:
        conversations = c.execute("SELECT id,title,updated_at FROM gw_ai_conversations WHERE user_id=%s ORDER BY updated_at DESC LIMIT 40", (session["user_id"],)).fetchall()
    return render_template("ai.html", conversations=conversations, conversation=None, messages=[])


@app.post("/ai/new")
@required
def ai_new_conversation():
    with db() as c:
        row = c.execute("INSERT INTO gw_ai_conversations(user_id,title) VALUES(%s,'New conversation') RETURNING id", (session["user_id"],)).fetchone()
    return redirect(url_for("ai_conversation", conversation_id=row["id"]))


@app.route("/ai/<int:conversation_id>")
@required
def ai_conversation(conversation_id):
    with db() as c:
        conversation = c.execute("SELECT id,user_id,title,created_at,updated_at FROM gw_ai_conversations WHERE id=%s AND user_id=%s", (conversation_id, session["user_id"])).fetchone()
        if not conversation:
            abort(404)
        messages = c.execute("SELECT id,role,content,created_at FROM gw_ai_messages WHERE conversation_id=%s ORDER BY created_at ASC LIMIT 100", (conversation_id,)).fetchall()
        conversations = c.execute("SELECT id,title,updated_at FROM gw_ai_conversations WHERE user_id=%s ORDER BY updated_at DESC LIMIT 40", (session["user_id"],)).fetchall()
    return render_template("ai.html", conversations=conversations, conversation=conversation, messages=messages)


@app.post("/ai/<int:conversation_id>/send")
@required
def ai_send_message(conversation_id):
    prompt = request.form.get("message", "").strip()
    if not prompt or len(prompt) > 2500:
        flash("Write a message of up to 2,500 characters.", "error")
        return redirect(url_for("ai_conversation", conversation_id=conversation_id))
    if not rate_limit_allowed("gemini_chat", 20, 3600, str(session.get("user_id"))):
        flash("You have reached the Gather AI hourly message limit. Please try later.", "error")
        return redirect(url_for("ai_conversation", conversation_id=conversation_id))
    with db() as c:
        conversation = c.execute("SELECT id,title FROM gw_ai_conversations WHERE id=%s AND user_id=%s", (conversation_id, session["user_id"])).fetchone()
        if not conversation:
            abort(404)
        prior = c.execute("SELECT role,content FROM gw_ai_messages WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 16", (conversation_id,)).fetchall()
    history = [{"role": row["role"], "parts": [{"text": row["content"]}]} for row in reversed(prior)]
    history.append({"role": "user", "parts": [{"text": prompt}]})
    try:
        reply = gemini_generate_reply(history)
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("ai_conversation", conversation_id=conversation_id))
    title = prompt[:72].strip()
    with db() as c:
        c.execute("INSERT INTO gw_ai_messages(conversation_id,role,content) VALUES(%s,'user',%s)", (conversation_id, prompt))
        c.execute("INSERT INTO gw_ai_messages(conversation_id,role,content) VALUES(%s,'model',%s)", (conversation_id, reply))
        c.execute("UPDATE gw_ai_conversations SET title=CASE WHEN title='New conversation' THEN %s ELSE title END,updated_at=NOW() WHERE id=%s AND user_id=%s", (title, conversation_id, session["user_id"]))
    return redirect(url_for("ai_conversation", conversation_id=conversation_id))


@app.post("/ai/<int:conversation_id>/delete")
@required
def ai_delete_conversation(conversation_id):
    with db() as c:
        c.execute("DELETE FROM gw_ai_conversations WHERE id=%s AND user_id=%s", (conversation_id, session["user_id"]))
    flash("AI conversation deleted.", "success")
    return redirect(url_for("ai_home"))


# -----------------------------------------------------------------------------
# PHASE 8 — CREATOR AND BUSINESS PAGES
# -----------------------------------------------------------------------------
CREATOR_CATEGORIES = ["Art & Design", "Education", "Gaming", "Music", "Photography", "Technology", "Writing", "Video", "Other"]
BUSINESS_CATEGORIES = ["Shopping", "Food", "Technology", "Education", "Health & Wellness", "Professional Services", "Travel", "Other"]


def optional_https_url(value):
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Enter a valid HTTPS website URL.")
    return value[:500]


@app.route("/creators")
def creators_directory():
    q = request.args.get("q", "").strip()[:80]
    pattern = f"%{q}%"
    with db() as c:
        creators = c.execute("""SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset,
            cp.headline,cp.category,cp.about,cp.website_url,cp.portfolio_url,
            (SELECT COUNT(*) FROM gw_follows f WHERE f.followed_id=u.id) AS followers
            FROM gw_creator_profiles cp JOIN gw_users u ON u.id=cp.user_id
            WHERE cp.is_public=TRUE AND u.is_suspended=FALSE
              AND (%s='' OR u.username ILIKE %s OR u.display_name ILIKE %s OR cp.category ILIKE %s OR cp.headline ILIKE %s)
            ORDER BY followers DESC,cp.updated_at DESC LIMIT 60""", (q, pattern, pattern, pattern, pattern)).fetchall()
    return render_template("creators.html", creators=creators, q=q)


@app.route("/creator/settings", methods=["GET", "POST"])
@required
def creator_settings():
    with db() as c:
        profile = c.execute("SELECT * FROM gw_creator_profiles WHERE user_id=%s", (session["user_id"],)).fetchone()
    if request.method == "POST":
        headline = request.form.get("headline", "").strip()[:120]
        category = request.form.get("category", "Other").strip()
        about = request.form.get("about", "").strip()[:1200]
        try:
            website = optional_https_url(request.form.get("website_url"))
            portfolio = optional_https_url(request.form.get("portfolio_url"))
            if category not in CREATOR_CATEGORIES:
                category = "Other"
            is_public = request.form.get("is_public") == "1"
            with db() as c:
                c.execute("""INSERT INTO gw_creator_profiles(user_id,headline,category,about,website_url,portfolio_url,is_public)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(user_id) DO UPDATE SET headline=EXCLUDED.headline,category=EXCLUDED.category,
                    about=EXCLUDED.about,website_url=EXCLUDED.website_url,portfolio_url=EXCLUDED.portfolio_url,
                    is_public=EXCLUDED.is_public,updated_at=NOW()""",
                    (session["user_id"], headline, category, about, website, portfolio, is_public))
            flash("Creator profile saved.", "success")
            return redirect(url_for("creator_dashboard"))
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception:
            app.logger.exception("Creator profile save failed")
            flash("Your creator profile could not be saved. Please try again.", "error")
        with db() as c:
            profile = c.execute("SELECT * FROM gw_creator_profiles WHERE user_id=%s", (session["user_id"],)).fetchone()
    return render_template("creator_settings.html", profile=profile, categories=CREATOR_CATEGORIES)


@app.route("/creator/dashboard")
@required
def creator_dashboard():
    with db() as c:
        profile = c.execute("SELECT * FROM gw_creator_profiles WHERE user_id=%s", (session["user_id"],)).fetchone()
        if not profile:
            return redirect(url_for("creator_settings"))
        stats = c.execute("""SELECT
            (SELECT COUNT(*) FROM gw_follows WHERE followed_id=%s) AS followers,
            (SELECT COUNT(*) FROM gw_posts WHERE user_id=%s) AS posts,
            (SELECT COUNT(*) FROM gw_creator_profile_views WHERE creator_id=%s AND viewed_at>=NOW()-INTERVAL '30 days') AS profile_views""",
            (session["user_id"], session["user_id"], session["user_id"])).fetchone()
    return render_template("creator_dashboard.html", profile=profile, stats=stats)


@app.route("/creator/<username>")
def creator_public(username):
    viewer_id = session.get("user_id")
    with db() as c:
        creator = c.execute("""SELECT u.id,u.username,u.display_name,u.bio,u.avatar_url,u.avatar_preset,
            cp.headline,cp.category,cp.about,cp.website_url,cp.portfolio_url,cp.is_public,
            (SELECT COUNT(*) FROM gw_follows WHERE followed_id=u.id) AS followers
            FROM gw_users u JOIN gw_creator_profiles cp ON cp.user_id=u.id
            WHERE u.username=%s AND u.is_suspended=FALSE""", (username.lower(),)).fetchone()
        if not creator or (not creator["is_public"] and creator["id"] != viewer_id):
            abort(404)
        if creator["id"] != viewer_id:
            c.execute("INSERT INTO gw_creator_profile_views(creator_id,viewer_id) VALUES(%s,%s)", (creator["id"], viewer_id))
        posts = c.execute("""SELECT p.*,
            (SELECT COUNT(*) FROM gw_likes WHERE post_id=p.id) AS likes,
            (SELECT COUNT(*) FROM gw_comments WHERE post_id=p.id) AS comments
            FROM gw_posts p WHERE p.user_id=%s ORDER BY p.created_at DESC LIMIT 30""", (creator["id"],)).fetchall()
        following = bool(viewer_id and c.execute("SELECT 1 FROM gw_follows WHERE follower_id=%s AND followed_id=%s", (viewer_id, creator["id"])).fetchone())
    return render_template("creator_public.html", creator=creator, posts=posts, following=following)


@app.route("/businesses")
def businesses_directory():
    q = request.args.get("q", "").strip()[:80]
    pattern = f"%{q}%"
    with db() as c:
        businesses = c.execute("""SELECT b.*,(SELECT username FROM gw_users WHERE id=b.owner_id) AS owner_username,
            (SELECT COUNT(*) FROM gw_business_follows bf WHERE bf.business_id=b.id) AS followers
            FROM gw_businesses b WHERE b.is_public=TRUE
              AND (%s='' OR b.name ILIKE %s OR b.category ILIKE %s OR b.description ILIKE %s OR b.location ILIKE %s)
            ORDER BY followers DESC,b.created_at DESC LIMIT 80""", (q, pattern, pattern, pattern, pattern)).fetchall()
    return render_template("businesses.html", businesses=businesses, q=q)


@app.route("/businesses/create", methods=["GET", "POST"])
@required
def business_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:90]
        slug = request.form.get("slug", "").strip().lower()[:50]
        category = request.form.get("category", "Other").strip()
        description = request.form.get("description", "").strip()[:1500]
        contact_email = request.form.get("contact_email", "").strip().lower()[:255]
        location = request.form.get("location", "").strip()[:140]
        try:
            website = optional_https_url(request.form.get("website_url"))
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("business_create.html", categories=BUSINESS_CATEGORIES)
        if not name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            flash("Add a business name and a URL nickname using lowercase letters, numbers and hyphens.", "error")
        elif category not in BUSINESS_CATEGORIES:
            category = "Other"
        elif contact_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact_email):
            flash("Enter a valid contact email address.", "error")
        else:
            try:
                with db() as c:
                    row = c.execute("""INSERT INTO gw_businesses(owner_id,name,slug,category,description,website_url,contact_email,location)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING slug""",
                        (session["user_id"], name, slug, category, description, website, contact_email, location)).fetchone()
                flash("Business page created. It is marked unverified until reviewed.", "success")
                return redirect(url_for("business_public", slug=row["slug"]))
            except psycopg.errors.UniqueViolation:
                flash("That business page nickname is already in use.", "error")
            except Exception:
                app.logger.exception("Business page creation failed")
                flash("The business page could not be created. Please try again.", "error")
    return render_template("business_create.html", categories=BUSINESS_CATEGORIES)


@app.route("/business/<slug>")
def business_public(slug):
    viewer_id = session.get("user_id")
    with db() as c:
        business = c.execute("""SELECT b.*,u.username AS owner_username,
            (SELECT COUNT(*) FROM gw_business_follows bf WHERE bf.business_id=b.id) AS followers
            FROM gw_businesses b JOIN gw_users u ON u.id=b.owner_id WHERE b.slug=%s AND u.is_suspended=FALSE""", (slug,)).fetchone()
        if not business or (not business["is_public"] and business["owner_id"] != viewer_id):
            abort(404)
        following = bool(viewer_id and c.execute("SELECT 1 FROM gw_business_follows WHERE business_id=%s AND user_id=%s", (business["id"], viewer_id)).fetchone())
        is_owner = bool(viewer_id and business["owner_id"] == viewer_id)
    return render_template("business_public.html", business=business, following=following, is_owner=is_owner)


@app.route("/business/<slug>/edit", methods=["GET", "POST"])
@required
def business_edit(slug):
    with db() as c:
        business = c.execute("SELECT * FROM gw_businesses WHERE slug=%s AND owner_id=%s", (slug, session["user_id"])).fetchone()
    if not business:
        abort(404)
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:90]
        category = request.form.get("category", "Other").strip()
        description = request.form.get("description", "").strip()[:1500]
        contact_email = request.form.get("contact_email", "").strip().lower()[:255]
        location = request.form.get("location", "").strip()[:140]
        try:
            website = optional_https_url(request.form.get("website_url"))
            if not name:
                raise ValueError("Business name is required.")
            if category not in BUSINESS_CATEGORIES:
                category = "Other"
            if contact_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact_email):
                raise ValueError("Enter a valid contact email address.")
            with db() as c:
                c.execute("""UPDATE gw_businesses SET name=%s,category=%s,description=%s,website_url=%s,
                    contact_email=%s,location=%s,is_public=%s,updated_at=NOW() WHERE id=%s AND owner_id=%s""",
                    (name, category, description, website, contact_email, location, request.form.get("is_public")=="1", business["id"], session["user_id"]))
            flash("Business page updated.", "success")
            return redirect(url_for("business_public", slug=slug))
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception:
            app.logger.exception("Business page update failed")
            flash("The business page could not be updated.", "error")
        with db() as c:
            business = c.execute("SELECT * FROM gw_businesses WHERE slug=%s AND owner_id=%s", (slug, session["user_id"])).fetchone()
    return render_template("business_edit.html", business=business, categories=BUSINESS_CATEGORIES)


@app.post("/business/<slug>/follow")
@required
def business_follow(slug):
    with db() as c:
        business = c.execute("SELECT id,is_public FROM gw_businesses WHERE slug=%s", (slug,)).fetchone()
        if not business or not business["is_public"]:
            abort(404)
        if c.execute("SELECT 1 FROM gw_business_follows WHERE business_id=%s AND user_id=%s", (business["id"], session["user_id"])).fetchone():
            c.execute("DELETE FROM gw_business_follows WHERE business_id=%s AND user_id=%s", (business["id"], session["user_id"]))
        else:
            c.execute("INSERT INTO gw_business_follows(business_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (business["id"], session["user_id"]))
    return redirect(url_for("business_public", slug=slug))


# -----------------------------------------------------------------------------
# PHASE 9 — SYSTEM READINESS
# -----------------------------------------------------------------------------
@app.route("/admin/system")
@admin_required
def admin_system_readiness():
    checks = [
        {"label": "Neon database configuration", "ok": bool(DATABASE_URL), "detail": "Database connection string is configured." if DATABASE_URL else "DATABASE_URL is missing from the private environment."},
        {"label": "Strong Flask secret", "ok": bool(os.getenv("FLASK_SECRET_KEY")) and os.getenv("FLASK_SECRET_KEY") != "dev-only-change-me", "detail": "A custom secret key is configured." if os.getenv("FLASK_SECRET_KEY") and os.getenv("FLASK_SECRET_KEY") != "dev-only-change-me" else "Set a strong, unique FLASK_SECRET_KEY before production."},
        {"label": "Cloudinary media storage", "ok": all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)), "detail": "Cloudinary credentials are configured." if all((CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET)) else "One or more Cloudinary settings are missing."},
        {"label": "Zoho SMTP", "ok": all((MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER)), "detail": "SMTP settings are configured." if all((MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER)) else "One or more SMTP settings are missing."},
        {"label": "Gemini AI", "ok": bool(GEMINI_API_KEY), "detail": "Gemini API key is configured." if GEMINI_API_KEY else "Gather AI remains disabled until GEMINI_API_KEY is added."},
        {"label": "Production cookie mode", "ok": app.config.get("SESSION_COOKIE_SECURE", False), "detail": "Secure session cookies are enabled." if app.config.get("SESSION_COOKIE_SECURE", False) else "Secure cookies are off for local HTTP testing; enable them for HTTPS production."},
    ]
    try:
        with db() as c:
            c.execute("SELECT 1")
        checks.append({"label": "Database responds", "ok": True, "detail": "A simple database query succeeded."})
    except Exception:
        checks.append({"label": "Database responds", "ok": False, "detail": "The database query failed. Check Neon availability and DATABASE_URL."})
    passed = sum(1 for check in checks if check["ok"])
    return render_template("admin_system.html", checks=checks, passed=passed, total=len(checks))


# -----------------------------------------------------------------------------
# PHASE 10 PREPARATION — PUBLIC INFORMATION AND AFFILIATE READINESS
# -----------------------------------------------------------------------------
AFFILIATE_STATUSES = {"research", "applied", "pending", "approved", "rejected", "paused"}

SHOP_CATEGORIES = ["Electronics", "Fashion", "Gaming", "Home & Living", "Watches", "Accessories", "Books", "Sports", "Beauty", "Other"]
SHOP_CURRENCIES = ["USD", "PKR", "GBP", "EUR", "AED", "SAR"]


def shop_public_product_query():
    return """SELECT p.*, ap.name AS partner_name, ap.slug AS partner_slug,
          (SELECT COUNT(*) FROM gw_shop_product_clicks pc WHERE pc.product_id=p.id) AS clicks
        FROM gw_shop_products p
        JOIN gw_affiliate_partners ap ON ap.id=p.partner_id
        WHERE p.status='published' AND ap.status='approved' AND p.affiliate_url IS NOT NULL
          AND p.affiliate_url LIKE 'https://%%'"""


def parse_shop_price(value, field_name):
    try:
        amount = Decimal((value or "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Enter a valid {field_name}.")
    if not amount.is_finite() or amount < 0 or amount > Decimal("9999999999.99"):
        raise ValueError(f"Enter a valid {field_name}.")
    return amount.quantize(Decimal("0.01"))


def get_public_shop_product(product_id):
    with db() as c:
        return c.execute(shop_public_product_query() + " AND p.id=%s", (product_id,)).fetchone()


@app.route("/shop")
def shop_home():
    q = request.args.get("q", "").strip()[:100]
    category = request.args.get("category", "").strip()[:60]
    sort = request.args.get("sort", "newest").strip().lower()
    sort_sql = {"newest": "p.created_at DESC", "price_low": "p.partner_price ASC", "price_high": "p.partner_price DESC", "popular": "clicks DESC"}.get(sort, "p.created_at DESC")
    pattern = f"%{q}%"
    with db() as c:
        products = c.execute(shop_public_product_query() + """
            AND (%s='' OR p.title ILIKE %s OR p.description ILIKE %s OR p.category ILIKE %s OR ap.name ILIKE %s)
            AND (%s='' OR p.category=%s)
            ORDER BY """ + sort_sql + " LIMIT 72", (q, pattern, pattern, pattern, pattern, category, category)).fetchall()
        categories = c.execute("""SELECT DISTINCT p.category FROM gw_shop_products p
            JOIN gw_affiliate_partners ap ON ap.id=p.partner_id
            WHERE p.status='published' AND ap.status='approved' AND p.affiliate_url IS NOT NULL
            ORDER BY p.category""").fetchall()
    return render_template("shop_home.html", products=products, categories=categories, shop_categories=SHOP_CATEGORIES, q=q, category=category, sort=sort)


@app.route("/shop/product/<slug>")
def shop_product_detail(slug):
    with db() as c:
        product = c.execute(shop_public_product_query() + " AND p.slug=%s", (slug,)).fetchone()
        if not product:
            abort(404)
        c.execute("INSERT INTO gw_shop_product_views(product_id,user_id) VALUES(%s,%s)", (product["id"], session.get("user_id")))
        if session.get("user_id"):
            saved = c.execute("SELECT 1 FROM gw_shop_wishlists WHERE user_id=%s AND product_id=%s", (session["user_id"], product["id"])).fetchone()
            in_cart = c.execute("SELECT 1 FROM gw_shop_cart_items WHERE user_id=%s AND product_id=%s", (session["user_id"], product["id"])).fetchone()
            alert = c.execute("SELECT target_price FROM gw_shop_price_alerts WHERE user_id=%s AND product_id=%s AND is_active=TRUE", (session["user_id"], product["id"])).fetchone()
        else:
            saved = in_cart = alert = None
    recent = session.get("shop_recent", [])
    recent = [int(x) for x in recent if str(x).isdigit() and int(x) != int(product["id"])]
    session["shop_recent"] = ([int(product["id"])] + recent)[:12]
    with db() as c:
        related = c.execute(shop_public_product_query() + " AND p.category=%s AND p.id<>%s ORDER BY p.created_at DESC LIMIT 4", (product["category"], product["id"])).fetchall()
    return render_template("shop_product.html", product=product, is_saved=bool(saved), in_cart=bool(in_cart), alert=alert, related=related)


@app.route("/shop/cart")
@required
def shop_cart():
    with db() as c:
        items = c.execute("""SELECT ci.id AS cart_item_id,ci.quantity,ci.added_at,p.id AS product_id,p.title,p.slug,p.image_url,p.currency,p.partner_price,p.affiliate_url,p.status AS product_status,ap.id AS partner_id,ap.name AS partner_name,ap.status AS partner_status
            FROM gw_shop_cart_items ci JOIN gw_shop_products p ON p.id=ci.product_id
            JOIN gw_affiliate_partners ap ON ap.id=p.partner_id
            WHERE ci.user_id=%s
            ORDER BY ap.name,p.title""", (session["user_id"],)).fetchall()
    groups = []
    for item in items:
        group = next((g for g in groups if g["partner_id"] == item["partner_id"]), None)
        if group is None:
            group = {"partner_id": item["partner_id"], "partner_name": item["partner_name"], "items": []}
            groups.append(group)
        group["items"].append(item)
    return render_template("shop_cart.html", groups=groups, item_count=len(items))


@app.post("/shop/cart/add/<int:product_id>")
@required
def shop_cart_add(product_id):
    if not rate_limit_allowed("shop_cart_add", 30, 60, str(session["user_id"])):
        flash("Please slow down and try adding that item again shortly.", "error")
        return redirect(url_for("shop_home"))
    product = get_public_shop_product(product_id)
    if not product:
        abort(404)
    with db() as c:
        c.execute("""INSERT INTO gw_shop_cart_items(user_id,product_id,quantity) VALUES(%s,%s,1)
            ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=LEAST(gw_shop_cart_items.quantity+1,10),updated_at=NOW()""", (session["user_id"], product_id))
    flash("Added to your Gather shopping cart. Checkout happens on the retailer's website.", "success")
    return redirect(url_for("shop_cart"))


@app.post("/shop/cart/update/<int:item_id>")
@required
def shop_cart_update(item_id):
    quantity = request.form.get("quantity", type=int)
    if quantity is None or quantity < 1 or quantity > 10:
        flash("Choose a quantity between 1 and 10.", "error")
    else:
        with db() as c:
            c.execute("UPDATE gw_shop_cart_items SET quantity=%s,updated_at=NOW() WHERE id=%s AND user_id=%s", (quantity, item_id, session["user_id"]))
        flash("Cart quantity updated.", "success")
    return redirect(url_for("shop_cart"))


@app.post("/shop/cart/remove/<int:item_id>")
@required
def shop_cart_remove(item_id):
    with db() as c:
        c.execute("DELETE FROM gw_shop_cart_items WHERE id=%s AND user_id=%s", (item_id, session["user_id"]))
    flash("Item removed from your cart.", "success")
    return redirect(url_for("shop_cart"))


@app.route("/shop/out/<int:product_id>")
def shop_partner_out(product_id):
    product = get_public_shop_product(product_id)
    if not product or not product.get("affiliate_url"):
        abort(404)
    # Revalidate the stored destination to prevent unsafe redirects if data was altered.
    try:
        target = optional_https_url(product["affiliate_url"])
    except ValueError:
        abort(404)
    with db() as c:
        c.execute("INSERT INTO gw_shop_product_clicks(product_id,user_id,clicked_at) VALUES(%s,%s,NOW())", (product_id, session.get("user_id")))
    return redirect(target, code=302)


@app.route("/shop/wishlist")
@required
def shop_wishlist():
    with db() as c:
        products = c.execute("""SELECT p.*,ap.name AS partner_name,ap.slug AS partner_slug,
            (SELECT COUNT(*) FROM gw_shop_product_clicks pc WHERE pc.product_id=p.id) AS clicks
            FROM gw_shop_wishlists w JOIN gw_shop_products p ON p.id=w.product_id
            JOIN gw_affiliate_partners ap ON ap.id=p.partner_id
            WHERE w.user_id=%s AND p.status='published' AND ap.status='approved' AND p.affiliate_url IS NOT NULL
            ORDER BY w.created_at DESC""", (session["user_id"],)).fetchall()
    return render_template("shop_wishlist.html", products=products)


@app.post("/shop/wishlist/toggle/<int:product_id>")
@required
def shop_wishlist_toggle(product_id):
    product = get_public_shop_product(product_id)
    if not product:
        abort(404)
    with db() as c:
        existing = c.execute("SELECT 1 FROM gw_shop_wishlists WHERE user_id=%s AND product_id=%s", (session["user_id"], product_id)).fetchone()
        if existing:
            c.execute("DELETE FROM gw_shop_wishlists WHERE user_id=%s AND product_id=%s", (session["user_id"], product_id))
            flash("Removed from your wishlist.", "success")
        else:
            c.execute("INSERT INTO gw_shop_wishlists(user_id,product_id) VALUES(%s,%s) ON CONFLICT DO NOTHING", (session["user_id"], product_id))
            flash("Saved to your wishlist.", "success")
    return redirect(url_for("shop_wishlist"))


@app.route("/shop/compare")
def shop_compare():
    compare_ids = session.get("shop_compare", [])
    compare_ids = [int(x) for x in compare_ids if str(x).isdigit()][:4]
    session["shop_compare"] = compare_ids
    if compare_ids:
        with db() as c:
            products = c.execute(shop_public_product_query() + " AND p.id = ANY(%s) ORDER BY p.partner_price ASC", (compare_ids,)).fetchall()
    else:
        products = []
    return render_template("shop_compare.html", products=products)


@app.post("/shop/compare/add/<int:product_id>")
def shop_compare_add(product_id):
    product = get_public_shop_product(product_id)
    if not product:
        abort(404)
    compare_ids = [int(x) for x in session.get("shop_compare", []) if str(x).isdigit()]
    if product_id not in compare_ids:
        if len(compare_ids) >= 4:
            flash("You can compare up to four products at a time.", "info")
        else:
            compare_ids.append(product_id)
            session["shop_compare"] = compare_ids
            flash("Product added to comparison.", "success")
    return redirect(url_for("shop_compare"))


@app.post("/shop/compare/remove/<int:product_id>")
def shop_compare_remove(product_id):
    session["shop_compare"] = [int(x) for x in session.get("shop_compare", []) if str(x).isdigit() and int(x) != product_id]
    flash("Product removed from comparison.", "success")
    return redirect(url_for("shop_compare"))


@app.post("/shop/compare/clear")
def shop_compare_clear():
    session["shop_compare"] = []
    flash("Comparison list cleared.", "success")
    return redirect(url_for("shop_compare"))


@app.route("/shop/deals")
def shop_deals():
    with db() as c:
        products = c.execute(shop_public_product_query() + " AND p.original_price IS NOT NULL AND p.original_price>p.partner_price ORDER BY (p.original_price-p.partner_price) DESC LIMIT 60").fetchall()
    return render_template("shop_deals.html", products=products)


@app.route("/shop/price-alerts", methods=["GET", "POST"])
@required
def shop_price_alerts():
    if request.method == "POST":
        product_id = request.form.get("product_id", type=int)
        try:
            target = parse_shop_price(request.form.get("target_price"), "target price")
            product = get_public_shop_product(product_id)
            if not product:
                raise ValueError("Choose an available product.")
            with db() as c:
                c.execute("""INSERT INTO gw_shop_price_alerts(user_id,product_id,target_price,is_active,notified_at)
                    VALUES(%s,%s,%s,TRUE,NULL)
                    ON CONFLICT(user_id,product_id) DO UPDATE SET target_price=EXCLUDED.target_price,is_active=TRUE,notified_at=NULL""", (session["user_id"], product_id, target))
            flash("Price alert saved. Alerts are checked when Gather records a product price update.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("shop_price_alerts"))
    with db() as c:
        alerts = c.execute("""SELECT a.id,a.target_price,a.is_active,a.notified_at,p.title,p.slug,p.currency,p.partner_price,p.image_url
            FROM gw_shop_price_alerts a JOIN gw_shop_products p ON p.id=a.product_id
            WHERE a.user_id=%s ORDER BY a.created_at DESC""", (session["user_id"],)).fetchall()
        products = c.execute(shop_public_product_query() + " ORDER BY p.title").fetchall()
    return render_template("shop_price_alerts.html", alerts=alerts, products=products)


@app.post("/shop/price-alerts/delete/<int:alert_id>")
@required
def shop_price_alert_delete(alert_id):
    with db() as c:
        c.execute("DELETE FROM gw_shop_price_alerts WHERE id=%s AND user_id=%s", (alert_id, session["user_id"]))
    flash("Price alert removed.", "success")
    return redirect(url_for("shop_price_alerts"))


@app.route("/shop/recently-viewed")
def shop_recently_viewed():
    if session.get("user_id"):
        with db() as c:
            products = c.execute("""SELECT p.*,ap.name AS partner_name,ap.slug AS partner_slug,
                (SELECT COUNT(*) FROM gw_shop_product_clicks pc WHERE pc.product_id=p.id) AS clicks
                FROM (SELECT product_id,MAX(viewed_at) AS last_viewed FROM gw_shop_product_views
                      WHERE user_id=%s GROUP BY product_id) v
                JOIN gw_shop_products p ON p.id=v.product_id JOIN gw_affiliate_partners ap ON ap.id=p.partner_id
                WHERE p.status='published' AND ap.status='approved' AND p.affiliate_url IS NOT NULL
                ORDER BY v.last_viewed DESC LIMIT 12""", (session["user_id"],)).fetchall()
    else:
        recent_ids = [int(x) for x in session.get("shop_recent", []) if str(x).isdigit()][:12]
        with db() as c:
            products = c.execute(shop_public_product_query() + " AND p.id=ANY(%s)", (recent_ids or [0],)).fetchall()
        order = {pid: i for i, pid in enumerate(recent_ids)}
        products.sort(key=lambda item: order.get(item["id"], 999))
    return render_template("shop_recently_viewed.html", products=products)


@app.route("/admin/shop-products", methods=["GET", "POST"])
@admin_required
def admin_shop_products():
    if request.method == "POST":
        action = (request.form.get("action") or "add").strip().lower()
        try:
            if action == "add":
                title = (request.form.get("title") or "").strip()[:140]
                slug = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:160]
                description = (request.form.get("description") or "").strip()[:4000]
                category = (request.form.get("category") or "Other").strip()
                partner_id = request.form.get("partner_id", type=int)
                image_url = optional_https_url(request.form.get("image_url", ""))
                affiliate_url = optional_https_url(request.form.get("affiliate_url", ""))
                price = parse_shop_price(request.form.get("partner_price"), "partner price")
                original_raw = (request.form.get("original_price") or "").strip()
                original = parse_shop_price(original_raw, "original price") if original_raw else None
                currency = (request.form.get("currency") or "USD").strip().upper()
                requested_status = (request.form.get("status") or "draft").strip().lower()
                if not title or not slug:
                    raise ValueError("Enter a product title.")
                if category not in SHOP_CATEGORIES:
                    raise ValueError("Choose a valid product category.")
                if currency not in SHOP_CURRENCIES:
                    raise ValueError("Choose a supported display currency.")
                if requested_status not in {"draft", "published", "paused"}:
                    raise ValueError("Choose a valid listing status.")
                if original is not None and original <= price:
                    raise ValueError("Original price must be higher than the current partner price.")
                if not affiliate_url and requested_status == "published":
                    raise ValueError("A product-specific approved HTTPS affiliate link is required before publishing.")
                with db() as c:
                    partner = c.execute("SELECT id,status FROM gw_affiliate_partners WHERE id=%s", (partner_id,)).fetchone()
                    if not partner:
                        raise ValueError("Select a valid retailer partner.")
                    if requested_status == "published" and partner["status"] != "approved":
                        raise ValueError("The retailer must be approved before products can be published.")
                    c.execute("""INSERT INTO gw_shop_products(partner_id,title,slug,description,category,image_url,currency,partner_price,original_price,affiliate_url,status,created_by)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (partner_id,title,slug,description,category,image_url,currency,price,original,affiliate_url or None,requested_status,session["user_id"]))
                flash("Product listing saved.", "success")
            elif action == "update":
                product_id = request.form.get("product_id", type=int)
                title = (request.form.get("title") or "").strip()[:140]
                description = (request.form.get("description") or "").strip()[:4000]
                category = (request.form.get("category") or "Other").strip()
                image_url = optional_https_url(request.form.get("image_url", ""))
                if not title or category not in SHOP_CATEGORIES:
                    raise ValueError("Enter a product title and choose a valid category.")
                new_price = parse_shop_price(request.form.get("partner_price"), "partner price")
                original_raw = (request.form.get("original_price") or "").strip()
                original = parse_shop_price(original_raw, "original price") if original_raw else None
                status = (request.form.get("status") or "draft").strip().lower()
                affiliate_url = optional_https_url(request.form.get("affiliate_url", ""))
                if status not in {"draft", "published", "paused"}:
                    raise ValueError("Choose a valid listing status.")
                if original is not None and original <= new_price:
                    raise ValueError("Original price must be higher than the current partner price.")
                with db() as c:
                    current = c.execute("SELECT p.id,p.partner_id,p.partner_price AS old_price,ap.status AS partner_status FROM gw_shop_products p JOIN gw_affiliate_partners ap ON ap.id=p.partner_id WHERE p.id=%s", (product_id,)).fetchone()
                    if not current:
                        raise ValueError("Product listing not found.")
                    if status == "published" and (current["partner_status"] != "approved" or not affiliate_url):
                        raise ValueError("Publishing requires an approved retailer and a product-specific HTTPS tracking URL.")
                    c.execute("""UPDATE gw_shop_products SET title=%s,description=%s,category=%s,image_url=%s,
                        partner_price=%s,original_price=%s,affiliate_url=%s,status=%s,updated_at=NOW() WHERE id=%s""",
                        (title,description,category,image_url,new_price,original,affiliate_url or None,status,product_id))
                    if new_price < current["old_price"]:
                        alerts = c.execute("""SELECT a.id,a.user_id,a.target_price,p.title,p.currency FROM gw_shop_price_alerts a JOIN gw_shop_products p ON p.id=a.product_id
                            WHERE a.product_id=%s AND a.is_active=TRUE AND a.notified_at IS NULL AND a.target_price >= %s""", (product_id,new_price)).fetchall()
                        for alert in alerts:
                            c.execute("INSERT INTO gw_notifications(recipient_id,actor_id,notification_type,entity_type,entity_id,message) VALUES(%s,NULL,'price_drop','shop_product',%s,%s)", (alert["user_id"],product_id,f"Price alert: {alert['title']} is now {alert['currency']} {new_price}."))
                        c.execute("UPDATE gw_shop_price_alerts SET notified_at=NOW(),is_active=FALSE WHERE product_id=%s AND is_active=TRUE AND notified_at IS NULL AND target_price >= %s", (product_id,new_price))
                flash("Product listing updated. Matching price alerts have been notified.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        except Exception:
            app.logger.exception("Shop product administration failed")
            flash("The product could not be saved. Check the fields and whether its slug already exists.", "error")
        return redirect(url_for("admin_shop_products"))
    with db() as c:
        partners = c.execute("SELECT id,name,status FROM gw_affiliate_partners WHERE slug IN ('daraz-pakistan','amazon-associates','ebay-partner-network') ORDER BY name").fetchall()
        products = c.execute("""SELECT p.*,ap.name AS partner_name,ap.status AS partner_status,
            (SELECT COUNT(*) FROM gw_shop_product_clicks pc WHERE pc.product_id=p.id) AS click_count
            FROM gw_shop_products p JOIN gw_affiliate_partners ap ON ap.id=p.partner_id
            ORDER BY p.updated_at DESC LIMIT 100""").fetchall()
    return render_template("admin_shop_products.html", partners=partners, products=products, categories=SHOP_CATEGORIES, currencies=SHOP_CURRENCIES)


@app.route("/partners")
def affiliate_partners_public():
    with db() as c:
        partners = c.execute("""SELECT name,website_url,affiliate_url
            FROM gw_affiliate_partners
            WHERE status='approved' AND affiliate_url IS NOT NULL
            ORDER BY name""").fetchall()
    return render_template("affiliate_partners.html", partners=partners)

@app.route("/admin/affiliate-partners", methods=["GET", "POST"])
@admin_required
def admin_affiliate_partners():
    if request.method == "POST":
        action = (request.form.get("action") or "add").strip().lower()
        if action == "add":
            name = (request.form.get("name") or "").strip()[:100]
            slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:70]
            status = (request.form.get("status") or "research").strip().lower()
            notes = (request.form.get("notes") or "").strip()[:1000]
            try:
                website_url = optional_https_url(request.form.get("website_url", ""))
                program_url = optional_https_url(request.form.get("program_url", ""))
                affiliate_url = optional_https_url(request.form.get("affiliate_url", ""))
                if not name or not slug:
                    raise ValueError("Enter a partner name.")
                if status not in AFFILIATE_STATUSES:
                    raise ValueError("Choose a valid partner status.")
                if affiliate_url and status != "approved":
                    raise ValueError("Add a tracking link only after the programme approves the application.")
                with db() as c:
                    c.execute("""INSERT INTO gw_affiliate_partners
                        (name,slug,website_url,program_url,status,affiliate_url,notes,applied_at,approved_at,created_by)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,
                          CASE WHEN %s='applied' OR %s='pending' THEN NOW() ELSE NULL END,
                          CASE WHEN %s='approved' THEN NOW() ELSE NULL END,%s)""",
                        (name,slug,website_url,program_url,status,affiliate_url or None,notes,status,status,status,session["user_id"]))
                flash("Partner added to the private programme tracker.", "success")
            except ValueError as exc:
                flash(str(exc), "error")
            except Exception:
                flash("That partner may already exist. Check the tracker and try again.", "error")
        elif action == "update":
            partner_id = request.form.get("partner_id", type=int)
            status = (request.form.get("status") or "research").strip().lower()
            notes = (request.form.get("notes") or "").strip()[:1000]
            try:
                affiliate_url = optional_https_url(request.form.get("affiliate_url", ""))
                if status not in AFFILIATE_STATUSES:
                    raise ValueError("Choose a valid partner status.")
                if affiliate_url and status != "approved":
                    raise ValueError("A tracking link can only be saved when the partner is approved.")
                with db() as c:
                    existing = c.execute("SELECT id FROM gw_affiliate_partners WHERE id=%s", (partner_id,)).fetchone()
                    if not existing:
                        raise ValueError("Partner record not found.")
                    c.execute("""UPDATE gw_affiliate_partners SET status=%s,notes=%s,
                        affiliate_url=%s,
                        applied_at=CASE WHEN %s IN ('applied','pending') AND applied_at IS NULL THEN NOW() ELSE applied_at END,
                        approved_at=CASE WHEN %s='approved' AND approved_at IS NULL THEN NOW() WHEN %s<>'approved' THEN NULL ELSE approved_at END,
                        updated_at=NOW() WHERE id=%s""",
                        (status,notes,affiliate_url or None,status,status,status,partner_id))
                flash("Partner record updated.", "success")
            except ValueError as exc:
                flash(str(exc), "error")
        return redirect(url_for("admin_affiliate_partners"))
    with db() as c:
        partners = c.execute("SELECT * FROM gw_affiliate_partners ORDER BY CASE status WHEN 'applied' THEN 1 WHEN 'pending' THEN 2 WHEN 'approved' THEN 3 ELSE 4 END, name").fetchall()
    return render_template("admin_affiliate_partners.html", partners=partners, statuses=sorted(AFFILIATE_STATUSES))


# -----------------------------------------------------------------------------
# PHASES 12–17 — SERVICES, FOOD, TRAVEL, LEARNING, CAREERS AND EVENTS
# The six modules share one simple listing model. Payments, delivery, bookings and
# course enrolments remain with the relevant provider until separate integrations
# and agreements are implemented.
# -----------------------------------------------------------------------------
DIRECTORY_MODULES = {
    "service": {
        "title": "Services & Freelancing", "singular": "service", "plural": "services",
        "intro": "Discover independent professionals, portfolios and useful services.",
        "create_title": "List a service", "create_hint": "Introduce your service clearly. Customers contact the provider directly.",
        "categories": ["Design", "Programming", "Writing", "Video & Animation", "Marketing", "Photography", "Business Support", "Other"],
        "create_endpoint": "services_create", "detail_endpoint": "service_detail", "directory_endpoint": "services_directory",
        "action_label": "View portfolio or service", "action_empty": "Contact provider",
        "kind_label": "Service listing", "cta": "Explore services"
    },
    "food": {
        "title": "Food & Local Commerce", "singular": "restaurant or local shop", "plural": "food and local listings",
        "intro": "Find restaurants, cafés, grocery stores and local food offers.",
        "create_title": "Add a restaurant or local shop", "create_hint": "Share accurate menu, location and ordering information. Orders are handled by the provider.",
        "categories": ["Restaurant", "Café", "Bakery", "Grocery", "Street Food", "Catering", "Other"],
        "create_endpoint": "food_create", "detail_endpoint": "food_detail", "directory_endpoint": "food_directory",
        "action_label": "View menu or order with provider", "action_empty": "Contact this business",
        "kind_label": "Local listing", "cta": "Explore food"
    },
    "travel": {
        "title": "Travel & Tourism", "singular": "travel listing", "plural": "travel listings",
        "intro": "Explore destinations, stays, activities and travel resources.",
        "create_title": "Add a travel listing", "create_hint": "Share a destination, accommodation or activity. Bookings stay with the listed provider.",
        "categories": ["Destination", "Hotel & Stay", "Activity", "Tour Operator", "Travel Guide", "Transport", "Other"],
        "create_endpoint": "travel_create", "detail_endpoint": "travel_detail", "directory_endpoint": "travel_directory",
        "action_label": "Continue to booking provider", "action_empty": "Contact provider",
        "kind_label": "Travel listing", "cta": "Explore travel"
    },
    "education": {
        "title": "Education & Learning", "singular": "learning resource", "plural": "learning resources",
        "intro": "Discover courses, tutorials, learning communities and educational resources.",
        "create_title": "Share a learning resource", "create_hint": "Recommend an educational resource and link to its official provider.",
        "categories": ["Technology", "Business", "Languages", "Design", "Science", "School & Study", "Professional Skills", "Other"],
        "create_endpoint": "learning_create", "detail_endpoint": "learning_detail", "directory_endpoint": "learning_directory",
        "action_label": "Open learning resource", "action_empty": "Contact provider",
        "kind_label": "Learning resource", "cta": "Explore learning"
    },
    "job": {
        "title": "Careers & Jobs", "singular": "job listing", "plural": "job listings",
        "intro": "Discover employment opportunities, internships and remote roles.",
        "create_title": "Post a job", "create_hint": "Post an accurate opportunity. Applications are handled by the employer or their application system.",
        "categories": ["Full-time", "Part-time", "Contract", "Internship", "Remote", "Freelance", "Other"],
        "create_endpoint": "career_create", "detail_endpoint": "career_detail", "directory_endpoint": "careers_directory",
        "action_label": "Apply on employer website", "action_empty": "Contact employer",
        "kind_label": "Employment listing", "cta": "Explore careers"
    },
    "event": {
        "title": "Events & Experiences", "singular": "event", "plural": "events",
        "intro": "Find community events, workshops, meetups and online experiences.",
        "create_title": "Create an event", "create_hint": "Share the schedule and venue or online location. RSVPs are managed by Gather World.",
        "categories": ["Community", "Workshop", "Conference", "Meetup", "Online", "Culture", "Sports", "Other"],
        "create_endpoint": "event_create", "detail_endpoint": "event_detail", "directory_endpoint": "events_directory",
        "action_label": "Open event website", "action_empty": "Contact organiser",
        "kind_label": "Event", "cta": "Explore events"
    },
}


def _directory_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug[:150].strip("-")


def _directory_list(kind):
    config = DIRECTORY_MODULES[kind]
    q = request.args.get("q", "").strip()[:80]
    category = request.args.get("category", "").strip()[:70]
    pattern = f"%{q}%"
    with db() as c:
        rows = c.execute("""SELECT e.*,u.username AS owner_username,u.display_name AS owner_display_name,
            u.avatar_url AS owner_avatar_url,u.avatar_preset AS owner_avatar_preset,
            CASE WHEN e.entry_kind='event' THEN (SELECT COUNT(*) FROM gw_directory_event_rsvps r WHERE r.entry_id=e.id AND r.response='going') ELSE 0 END AS going_count
            FROM gw_directory_entries e JOIN gw_users u ON u.id=e.owner_id
            WHERE e.entry_kind=%s AND e.is_active=TRUE AND u.is_suspended=FALSE
              AND (%s='' OR e.title ILIKE %s OR e.summary ILIKE %s OR e.description ILIKE %s OR e.category ILIKE %s OR e.location ILIKE %s)
              AND (%s='' OR e.category=%s)
            ORDER BY e.is_featured DESC, e.created_at DESC LIMIT 80""",
            (kind,q,pattern,pattern,pattern,pattern,pattern,category,category)).fetchall()
    return render_template("directory_home.html", module=config, entries=rows, q=q, selected_category=category, kind=kind)


def _directory_create(kind):
    config = DIRECTORY_MODULES[kind]
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:140]
        slug = _directory_slug(request.form.get("slug", "") or title)
        category = request.form.get("category", "Other").strip()[:70]
        summary = request.form.get("summary", "").strip()[:260]
        description = request.form.get("description", "").strip()[:6000]
        location = request.form.get("location", "").strip()[:180]
        price_label = request.form.get("price_label", "").strip()[:80]
        contact_email = request.form.get("contact_email", "").strip().lower()[:255]
        try:
            external_url = optional_https_url(request.form.get("external_url", ""))
            image_url = optional_https_url(request.form.get("image_url", ""))
            starts_at = None
            ends_at = None
            if kind == "event":
                raw_start = request.form.get("event_starts_at", "").strip()
                raw_end = request.form.get("event_ends_at", "").strip()
                if not raw_start:
                    raise ValueError("Add the event start date and time.")
                try:
                    parsed_start = datetime.fromisoformat(raw_start)
                    parsed_end = datetime.fromisoformat(raw_end) if raw_end else None
                except ValueError:
                    raise ValueError("Enter a valid event date and time.")
                if parsed_start.tzinfo is None:
                    parsed_start = parsed_start.astimezone()
                starts_at = parsed_start.astimezone(timezone.utc)
                if parsed_end:
                    if parsed_end.tzinfo is None:
                        parsed_end = parsed_end.astimezone()
                    ends_at = parsed_end.astimezone(timezone.utc)
                    if ends_at <= starts_at:
                        raise ValueError("The event end must be after its start.")
            if not title or len(title) < 3:
                raise ValueError("Enter a title with at least three characters.")
            if not slug:
                raise ValueError("Add a valid URL nickname or title.")
            if not summary:
                raise ValueError("Add a short summary so people know what this listing offers.")
            if category not in config["categories"]:
                raise ValueError("Choose a category from the list.")
            if contact_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact_email):
                raise ValueError("Enter a valid contact email address.")
            if not rate_limit_allowed("directory_create", 8, 3600, identity=str(session["user_id"])):
                raise ValueError("You have created several listings recently. Please try again later.")
            with db() as c:
                row = c.execute("""INSERT INTO gw_directory_entries
                    (entry_kind,owner_id,title,slug,category,summary,description,location,price_label,external_url,contact_email,image_url,event_starts_at,event_ends_at)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING slug""",
                    (kind,session["user_id"],title,slug,category,summary,description,location,price_label,external_url,contact_email,image_url,starts_at,ends_at)).fetchone()
            flash(f"Your {config['singular']} is now listed. It is marked as community-submitted and not independently verified by Gather World.", "success")
            return redirect(url_for(config["detail_endpoint"], slug=row["slug"]))
        except ValueError as exc:
            flash(str(exc), "error")
        except psycopg.errors.UniqueViolation:
            flash("That listing URL nickname is already in use. Try another one.", "error")
        except Exception:
            app.logger.exception("Directory listing creation failed for %s", kind)
            flash("The listing could not be saved. Please check the details and try again.", "error")
    return render_template("directory_create.html", module=config, kind=kind)


def _directory_detail(kind, slug):
    viewer_id = session.get("user_id")
    with db() as c:
        entry = c.execute("""SELECT e.*,u.username AS owner_username,u.display_name AS owner_display_name,
            u.avatar_url AS owner_avatar_url,u.avatar_preset AS owner_avatar_preset
            FROM gw_directory_entries e JOIN gw_users u ON u.id=e.owner_id
            WHERE e.entry_kind=%s AND e.slug=%s AND e.is_active=TRUE AND u.is_suspended=FALSE""",
            (kind,slug)).fetchone()
        if not entry:
            abort(404)
        going_count = 0
        interested_count = 0
        my_rsvp = None
        if kind == "event":
            counts = c.execute("""SELECT COUNT(*) FILTER (WHERE response='going') AS going_count,
                COUNT(*) FILTER (WHERE response='interested') AS interested_count
                FROM gw_directory_event_rsvps WHERE entry_id=%s""", (entry["id"],)).fetchone()
            going_count = counts["going_count"] or 0
            interested_count = counts["interested_count"] or 0
            if viewer_id:
                rsvp = c.execute("SELECT response FROM gw_directory_event_rsvps WHERE entry_id=%s AND user_id=%s", (entry["id"],viewer_id)).fetchone()
                my_rsvp = rsvp["response"] if rsvp else None
    return render_template("directory_detail.html", module=DIRECTORY_MODULES[kind], entry=entry, kind=kind,
                           going_count=going_count, interested_count=interested_count, my_rsvp=my_rsvp,
                           is_owner=bool(viewer_id and int(viewer_id)==int(entry["owner_id"])))


def _service_contact(slug):
    with db() as c:
        entry = c.execute("SELECT id,owner_id,title,slug FROM gw_directory_entries WHERE entry_kind='service' AND slug=%s AND is_active=TRUE", (slug,)).fetchone()
    if not entry:
        abort(404)
    message = request.form.get("message", "").strip()[:1800]
    if len(message) < 10:
        flash("Please write a little more so the provider understands your request.", "error")
        return redirect(url_for("service_detail", slug=slug))
    if entry["owner_id"] == session["user_id"]:
        flash("You cannot send an inquiry to your own listing.", "info")
        return redirect(url_for("service_detail", slug=slug))
    if not rate_limit_allowed("service_inquiry", 5, 3600, identity=f"{session['user_id']}:{entry['id']}" ):
        flash("You have sent several requests for this listing. Try again later.", "error")
        return redirect(url_for("service_detail", slug=slug))
    with db() as c:
        c.execute("INSERT INTO gw_service_inquiries(entry_id,sender_id,message) VALUES(%s,%s,%s)", (entry["id"],session["user_id"],message))
        create_notification(c,entry["owner_id"],session["user_id"],"service_inquiry","directory_entry",entry["id"],f"New inquiry about {entry['title']}")
    flash("Your inquiry was sent to the service provider.", "success")
    return redirect(url_for("service_detail", slug=slug))


def _directory_rsvp(slug):
    response = request.form.get("response", "going").strip().lower()
    if response not in {"going", "interested", "none"}:
        abort(400)
    with db() as c:
        entry = c.execute("SELECT id,owner_id,title FROM gw_directory_entries WHERE entry_kind='event' AND slug=%s AND is_active=TRUE", (slug,)).fetchone()
        if not entry:
            abort(404)
        if response == "none":
            c.execute("DELETE FROM gw_directory_event_rsvps WHERE entry_id=%s AND user_id=%s", (entry["id"],session["user_id"]))
            flash("Your event response was removed.", "success")
        else:
            c.execute("""INSERT INTO gw_directory_event_rsvps(entry_id,user_id,response) VALUES(%s,%s,%s)
                ON CONFLICT(entry_id,user_id) DO UPDATE SET response=EXCLUDED.response,updated_at=NOW()""",
                (entry["id"],session["user_id"],response))
            if response == "going":
                create_notification(c,entry["owner_id"],session["user_id"],"event_rsvp","directory_entry",entry["id"],f"Someone is going to {entry['title']}")
            flash("Your event response has been saved.", "success")
    return redirect(url_for("event_detail", slug=slug))


@app.route("/services")
def services_directory():
    return _directory_list("service")

@app.route("/services/create", methods=["GET", "POST"])
@required
def services_create():
    return _directory_create("service")

@app.route("/services/<slug>")
def service_detail(slug):
    return _directory_detail("service",slug)

@app.post("/services/<slug>/contact")
@required
def service_contact(slug):
    return _service_contact(slug)

@app.route("/food")
def food_directory():
    return _directory_list("food")

@app.route("/food/create", methods=["GET", "POST"])
@required
def food_create():
    return _directory_create("food")

@app.route("/food/<slug>")
def food_detail(slug):
    return _directory_detail("food",slug)

@app.route("/travel")
def travel_directory():
    return _directory_list("travel")

@app.route("/travel/create", methods=["GET", "POST"])
@required
def travel_create():
    return _directory_create("travel")

@app.route("/travel/<slug>")
def travel_detail(slug):
    return _directory_detail("travel",slug)

@app.route("/learn")
def learning_directory():
    return _directory_list("education")

@app.route("/learn/create", methods=["GET", "POST"])
@required
def learning_create():
    return _directory_create("education")

@app.route("/learn/<slug>")
def learning_detail(slug):
    return _directory_detail("education",slug)

@app.route("/careers")
def careers_directory():
    return _directory_list("job")

@app.route("/careers/post", methods=["GET", "POST"])
@required
def career_create():
    return _directory_create("job")

@app.route("/careers/<slug>")
def career_detail(slug):
    return _directory_detail("job",slug)

@app.route("/careers/<slug>/apply")
def career_apply(slug):
    with db() as c:
        entry = c.execute("SELECT external_url FROM gw_directory_entries WHERE entry_kind='job' AND slug=%s AND is_active=TRUE", (slug,)).fetchone()
    if not entry or not entry["external_url"]:
        abort(404)
    return redirect(entry["external_url"], code=302)

@app.route("/events")
def events_directory():
    return _directory_list("event")

@app.route("/events/create", methods=["GET", "POST"])
@required
def event_create():
    return _directory_create("event")

@app.route("/events/<slug>")
def event_detail(slug):
    return _directory_detail("event",slug)

@app.post("/events/<slug>/rsvp")
@required
def event_rsvp(slug):
    return _directory_rsvp(slug)

@app.route("/my-listings")
@required
def my_directory_listings():
    with db() as c:
        entries = c.execute("""SELECT id,entry_kind,title,slug,category,location,is_active,created_at
            FROM gw_directory_entries WHERE owner_id=%s ORDER BY created_at DESC LIMIT 120""", (session["user_id"],)).fetchall()
    return render_template("my_directory_listings.html", entries=entries)

@app.route("/directory-listings/<int:entry_id>/edit", methods=["GET", "POST"])
@required
def directory_listing_edit(entry_id):
    with db() as c:
        entry = c.execute("SELECT * FROM gw_directory_entries WHERE id=%s AND owner_id=%s", (entry_id,session["user_id"])).fetchone()
    if not entry:
        abort(404)
    kind = entry["entry_kind"]
    config = DIRECTORY_MODULES[kind]
    if request.method == "POST":
        title = request.form.get("title", "").strip()[:140]
        category = request.form.get("category", "Other").strip()[:70]
        summary = request.form.get("summary", "").strip()[:260]
        description = request.form.get("description", "").strip()[:6000]
        location = request.form.get("location", "").strip()[:180]
        price_label = request.form.get("price_label", "").strip()[:80]
        contact_email = request.form.get("contact_email", "").strip().lower()[:255]
        try:
            external_url = optional_https_url(request.form.get("external_url", ""))
            image_url = optional_https_url(request.form.get("image_url", ""))
            starts_at = entry["event_starts_at"]
            ends_at = entry["event_ends_at"]
            if kind == "event":
                raw_start = request.form.get("event_starts_at", "").strip()
                raw_end = request.form.get("event_ends_at", "").strip()
                if not raw_start:
                    raise ValueError("Add the event start date and time.")
                starts_at = datetime.fromisoformat(raw_start)
                ends_at = datetime.fromisoformat(raw_end) if raw_end else None
                if starts_at.tzinfo is None:
                    starts_at = starts_at.astimezone()
                starts_at = starts_at.astimezone(timezone.utc)
                if ends_at:
                    if ends_at.tzinfo is None:
                        ends_at = ends_at.astimezone()
                    ends_at = ends_at.astimezone(timezone.utc)
                    if ends_at <= starts_at:
                        raise ValueError("The event end must be after its start.")
            if len(title) < 3 or not summary:
                raise ValueError("Enter a title of at least three characters and a short summary.")
            if category not in config["categories"]:
                raise ValueError("Choose a valid category.")
            if contact_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", contact_email):
                raise ValueError("Enter a valid contact email address.")
            with db() as c:
                c.execute("""UPDATE gw_directory_entries SET title=%s,category=%s,summary=%s,description=%s,
                    location=%s,price_label=%s,external_url=%s,contact_email=%s,image_url=%s,
                    event_starts_at=%s,event_ends_at=%s,updated_at=NOW()
                    WHERE id=%s AND owner_id=%s""",
                    (title,category,summary,description,location,price_label,external_url,contact_email,image_url,
                     starts_at,ends_at,entry_id,session["user_id"]))
            flash("Your listing has been updated.", "success")
            return redirect(url_for(config["detail_endpoint"], slug=entry["slug"]))
        except (ValueError, TypeError) as exc:
            flash(str(exc) or "Check the date and time fields.", "error")
        except Exception:
            app.logger.exception("Directory listing update failed")
            flash("The listing could not be updated. Please try again.", "error")
    return render_template("directory_edit.html", module=config, kind=kind, entry=entry)


@app.route("/services/<slug>/inquiries")
@required
def service_inquiries(slug):
    with db() as c:
        entry = c.execute("SELECT id,title,slug,owner_id FROM gw_directory_entries WHERE entry_kind='service' AND slug=%s AND owner_id=%s", (slug,session["user_id"])).fetchone()
        if not entry:
            abort(404)
        inquiries = c.execute("""SELECT i.*,u.username,u.display_name,u.avatar_url,u.avatar_preset
            FROM gw_service_inquiries i JOIN gw_users u ON u.id=i.sender_id
            WHERE i.entry_id=%s ORDER BY i.created_at DESC LIMIT 100""", (entry["id"],)).fetchall()
    return render_template("service_inquiries.html", entry=entry, inquiries=inquiries)


@app.post("/directory-listings/<int:entry_id>/visibility")
@required
def directory_listing_visibility(entry_id):
    with db() as c:
        row = c.execute("SELECT id,entry_kind,is_active FROM gw_directory_entries WHERE id=%s AND owner_id=%s", (entry_id,session["user_id"])).fetchone()
        if not row:
            abort(404)
        c.execute("UPDATE gw_directory_entries SET is_active=NOT is_active,updated_at=NOW() WHERE id=%s", (entry_id,))
    flash("Listing visibility updated.", "success")
    return redirect(url_for("my_directory_listings"))

@app.route("/admin/directory-listings", methods=["GET", "POST"])
@admin_required
def admin_directory_listings():
    if request.method == "POST":
        entry_id = request.form.get("entry_id", type=int)
        action = request.form.get("action", "pause")
        with db() as c:
            if action == "activate":
                c.execute("UPDATE gw_directory_entries SET is_active=TRUE,updated_at=NOW() WHERE id=%s", (entry_id,))
            else:
                c.execute("UPDATE gw_directory_entries SET is_active=FALSE,updated_at=NOW() WHERE id=%s", (entry_id,))
        flash("Directory listing moderation updated.", "success")
        return redirect(url_for("admin_directory_listings"))
    with db() as c:
        entries = c.execute("""SELECT e.*,u.username AS owner_username FROM gw_directory_entries e
            JOIN gw_users u ON u.id=e.owner_id ORDER BY e.created_at DESC LIMIT 200""").fetchall()
    return render_template("admin_directory_listings.html", entries=entries)


@app.route("/<page>")
def starter(page):
    pages={"about":"About","explore":"Explore","community":"Community","news":"News","events":"Events","groups":"Groups","messages":"Messages","help":"Help Center","contact":"Contact","privacy":"Privacy Policy","terms":"Terms of Use","guidelines":"Community Guidelines","creators":"Creators","business":"Business","developers":"Developers","careers":"Careers","press":"Press","safety":"Safety","status":"Status","feedback":"Feedback","affiliate-disclosure":"Affiliate Disclosure"}
    if page not in pages:return render_template("404.html"),404
    dedicated = {
        "about": "public_about.html",
        "contact": "public_contact.html",
        "privacy": "public_privacy.html",
        "terms": "public_terms.html",
        "affiliate-disclosure": "affiliate_disclosure.html",
    }
    return render_template(dedicated.get(page, "page.html"), title=pages[page])
@app.errorhandler(400)
def bad_request(error):
    return render_template("error.html", code=400, title="Form security check", message=getattr(error, "description", "Please refresh the page and try again.")), 400

@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, title="Access restricted", message="You do not have permission to open this page."), 403

@app.errorhandler(404)
def missing(e):return render_template("404.html"),404
if __name__=="__main__":init_db();app.run(host="127.0.0.1",port=int(os.getenv("PORT","5000")),debug=os.getenv("FLASK_DEBUG","1").strip()=="1")
