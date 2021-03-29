-- rename username -> joiner
ALTER TABLE "monitored_chats"
RENAME COLUMN "username" TO "joiner";

-- add new column
ALTER TABLE "monitored_chats"
ADD COLUMN "title" text;

-- fill with default vals
UPDATE "monitored_chats"
SET "title"='placeholder_1141_fill_me';

-- add constraint
ALTER TABLE "monitored_chats"
ALTER COLUMN "title" SET NOT NULL;

-- now run follow on all these chats so title gets updated
