## ADDED Requirements

### Requirement: filtered Supabase delete

`SupabaseConnector` SHALL provide a filtered delete operation that returns a typed success,
table, row-count, and error result without exposing row contents in audit logs.

#### Scenario: delete a supplied stale-path set

- **Given** a caller supplies a table and a non-empty membership filter
- **When** the connector executes the delete
- **Then** it deletes only rows matching the filter, returns success with the supplied row
  count, and audits only operation metadata.

#### Scenario: reject an unfiltered delete

- **Given** a caller supplies neither equality nor membership filters
- **When** it requests deletion
- **Then** the connector returns a failed typed result without issuing a database operation.
