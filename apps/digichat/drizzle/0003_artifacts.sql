CREATE TABLE "artifacts" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"conversation_id" uuid NOT NULL,
	"token" text NOT NULL,
	"name" text NOT NULL,
	"media_type" text NOT NULL,
	"byte_size" integer NOT NULL,
	"storage_key" text NOT NULL,
	"kind" text DEFAULT 'file' NOT NULL,
	"summary" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "artifacts" ADD CONSTRAINT "artifacts_conversation_id_conversations_id_fk" FOREIGN KEY ("conversation_id") REFERENCES "public"."conversations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "artifacts_token" ON "artifacts" USING btree ("token");--> statement-breakpoint
CREATE UNIQUE INDEX "artifacts_storage_key" ON "artifacts" USING btree ("storage_key");--> statement-breakpoint
CREATE INDEX "artifacts_conversation_created" ON "artifacts" USING btree ("conversation_id","created_at");
