-- TABLES
-- chats
DROP TABLE IF EXISTS "chats" CASCADE;
CREATE TABLE "chats" (
	"id" serial8,
	"telegram_chat_id" int8 NOT NULL,
	"chat_type" int2 NOT NULL,
	CONSTRAINT "chats_pk" PRIMARY KEY ("id"),
	CONSTRAINT "chats_telegram_chat_id_unique" UNIQUE ("telegram_chat_id")
);

-- user chats
DROP TABLE IF EXISTS "user_chats" CASCADE;
CREATE TABLE "user_chats" (
	"id" serial8,
	"chats_id" int8 NOT NULL,
	"language" int2 NOT NULL,
	"enabled" boolean NOT NULL DEFAULT TRUE,
	CONSTRAINT "user_chats_pk" PRIMARY KEY ("id"),
	CONSTRAINT "user_chats_fk_chats" FOREIGN KEY ("chats_id") REFERENCES "chats"("id"),
	CONSTRAINT "user_chats_chats_id_unique" UNIQUE ("chats_id")
);

-- subbed chats
DROP TABLE IF EXISTS "monitored_chats" CASCADE;
CREATE TABLE "monitored_chats" (
	"id" serial8,
	"chats_id" int8 NOT NULL,
	"title" text NOT NULL,
	"joiner" text NOT NULL, -- username or joinchat link
	"enabled" boolean NOT NULL DEFAULT TRUE,
	"modification_time" timestamp with time zone NOT NULL DEFAULT NOW(), -- use with statement_timeout (set local!)
	CONSTRAINT "monitored_chats_pk" PRIMARY KEY ("id"),
	CONSTRAINT "monitored_chats_fk_chats" FOREIGN KEY ("chats_id") REFERENCES "chats"("id"),
	CONSTRAINT "monitored_chats_chats_id_unique" UNIQUE ("chats_id")
);

-- subscriptions
DROP TABLE IF EXISTS "subscriptions" CASCADE;
CREATE TABLE "subscriptions" (
	"id" serial8,
	"user_chats_id" int8 NOT NULL,
	"monitored_chats_id" int8 NOT NULL,
	"enabled" boolean NOT NULL DEFAULT TRUE,
	"modification_time" timestamp with time zone NOT NULL DEFAULT NOW(), -- use with statement_timeout (set local!)
	CONSTRAINT "subscriptions_pk" PRIMARY KEY ("id"),
	CONSTRAINT "subscriptions_fk_user_chats" FOREIGN KEY ("user_chats_id") REFERENCES "user_chats"("id"),
	CONSTRAINT "subscriptions_fk_monitored_chats" FOREIGN KEY ("monitored_chats_id") REFERENCES "monitored_chats"("id"),
	CONSTRAINT "subscriptions_user_monitored_chats_is_unique" UNIQUE ("monitored_chats_id", "user_chats_id")
);

-- FUNCTIONS
CREATE OR REPLACE FUNCTION monitored_chats_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.modification_time = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION function_notify_subscriptions_updated()
RETURNS TRIGGER AS $$
BEGIN
  NOTIFY notify_subscriptions_updated;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- TRIGGERS
DROP TRIGGER IF EXISTS set_timestamp on "monitored_chats";
CREATE TRIGGER set_timestamp
BEFORE UPDATE ON "monitored_chats"
FOR EACH ROW
EXECUTE PROCEDURE monitored_chats_update_timestamp();

DROP TRIGGER IF EXISTS subscriptions_updated on "subscriptions";
CREATE TRIGGER subscriptions_updated
AFTER UPDATE OR INSERT ON "subscriptions"
EXECUTE PROCEDURE function_notify_subscriptions_updated();

-- INDEXES
-- for is enrolled lookup
DROP INDEX IF EXISTS chats_telegram_user_id_hash;
CREATE INDEX chats_telegram_user_id_hash ON "chats" USING HASH ("telegram_chat_id");
DROP INDEX IF EXISTS user_chats_telegram_user_id_hash;
CREATE INDEX user_chats_telegram_user_id_hash ON "user_chats" USING HASH ("chats_id");

-- for is monitored lookup
DROP INDEX IF EXISTS monitored_chats_telegram_chat_id_hash;
CREATE INDEX monitored_chats_telegram_chat_id_hash ON "monitored_chats" USING HASH ("chats_id");
DROP INDEX IF EXISTS monitored_chats_modification_time_btree;
CREATE INDEX monitored_chats_modification_time_btree ON "monitored_chats" USING BTREE ("modification_time");

-- for subscriptions table result lookup
DROP INDEX IF EXISTS chats_id_hash;
CREATE INDEX chats_id_hash ON "chats" USING HASH ("id");
DROP INDEX IF EXISTS user_chats_id_hash;
CREATE INDEX user_chats_id_hash ON "user_chats" USING HASH ("id");
DROP INDEX IF EXISTS monitored_chats_id_hash;
CREATE INDEX monitored_chats_id_hash ON "monitored_chats" USING HASH ("id");
DROP INDEX IF EXISTS subscriptions_btree_multi;
CREATE INDEX subscriptions_btree_multi ON "subscriptions" USING BTREE ("monitored_chats_id", "user_chats_id");
-- mb add hash on subscriptions.users_id to delete users faster?