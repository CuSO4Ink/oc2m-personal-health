CREATE TABLE `grants` (
	`id` text PRIMARY KEY NOT NULL,
	`tenant` text NOT NULL,
	`owner` text NOT NULL,
	`doctor` text NOT NULL,
	`record_id` text NOT NULL,
	`expires` text NOT NULL,
	`created` text NOT NULL,
	`revoked` text,
	FOREIGN KEY (`record_id`) REFERENCES `records`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `grants_access` ON `grants` (`tenant`,`doctor`,`record_id`);--> statement-breakpoint
CREATE TABLE `logs` (
	`id` text PRIMARY KEY NOT NULL,
	`tenant` text NOT NULL,
	`owner` text NOT NULL,
	`actor` text NOT NULL,
	`record_id` text,
	`title` text NOT NULL,
	`action` text NOT NULL,
	`result` text NOT NULL,
	`created` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `logs_owner` ON `logs` (`tenant`,`owner`,`created`);--> statement-breakpoint
CREATE TABLE `records` (
	`id` text PRIMARY KEY NOT NULL,
	`tenant` text NOT NULL,
	`owner` text NOT NULL,
	`title` text NOT NULL,
	`kind` text NOT NULL,
	`date` text NOT NULL,
	`source` text NOT NULL,
	`summary` text NOT NULL,
	`version` integer DEFAULT 1 NOT NULL,
	`created` text NOT NULL,
	`updated` text NOT NULL,
	`file_key` text,
	`file_name` text,
	`file_type` text,
	`file_size` integer
);
--> statement-breakpoint
CREATE INDEX `records_owner` ON `records` (`tenant`,`owner`);--> statement-breakpoint
CREATE TABLE `sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`tenant` text NOT NULL,
	`actor` text NOT NULL,
	`expires` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `versions` (
	`id` text PRIMARY KEY NOT NULL,
	`record_id` text NOT NULL,
	`tenant` text NOT NULL,
	`version` integer NOT NULL,
	`title` text NOT NULL,
	`summary` text NOT NULL,
	`actor` text NOT NULL,
	`created` text NOT NULL,
	FOREIGN KEY (`record_id`) REFERENCES `records`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE UNIQUE INDEX `versions_record_number` ON `versions` (`record_id`,`version`);