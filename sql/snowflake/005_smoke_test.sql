-- Only in an isolated demo schema. Uses synthetic snapshots and versioned IDs.
INSERT INTO APPLICATION_EVENTS VALUES
 ('SYN-e1','SYN-a1',1,'2025-01-01 09:00:00','refer','pending','broker'),
 ('SYN-e2','SYN-a1',2,'2025-01-01 10:00:00','reviewed','standard','broker');
CALL PROCESS_APPLICATION_EVENTS();
-- Expect 5 changed fields across initial snapshot and update.
SELECT COUNT(*) AS SHOULD_BE_5 FROM DECISION_DELTAS WHERE APPLICATION_ID='SYN-a1';
-- Exact replay should produce no additional delta rows.
INSERT INTO APPLICATION_EVENTS VALUES ('SYN-e2','SYN-a1',2,'2025-01-01 10:00:00','reviewed','standard','broker');
CALL PROCESS_APPLICATION_EVENTS();
SELECT COUNT(*) AS STILL_5 FROM DECISION_DELTAS WHERE APPLICATION_ID='SYN-a1';
