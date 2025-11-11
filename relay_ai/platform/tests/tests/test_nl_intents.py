"""Tests for Natural Language Intent Parser."""


from relay_ai.nl.intents import Intent, parse_intent, validate_intent


class TestVerbExtraction:
    """Test verb extraction from commands."""

    def test_email_verb(self):
        """Test email verb detection."""
        intent = parse_intent("Email the report to alice@example.com")
        assert intent.verb == "email"

        intent = parse_intent("Send an email to bob@example.com")
        assert intent.verb == "email"

    def test_message_verb(self):
        """Test message verb detection."""
        intent = parse_intent("Message Alice about the meeting")
        assert intent.verb == "message"

        intent = parse_intent("Send a message to Bob")
        assert intent.verb == "message"

        intent = parse_intent("Ping Charlie")
        assert intent.verb == "message"

    def test_forward_verb(self):
        """Test forward verb detection."""
        intent = parse_intent("Forward this email to the team")
        assert intent.verb == "forward"

        intent = parse_intent("Share the document with Alice")
        assert intent.verb == "forward"

    def test_reply_verb(self):
        """Test reply verb detection."""
        intent = parse_intent("Reply to Bob's message")
        assert intent.verb == "reply"

        intent = parse_intent("Respond to the email")
        assert intent.verb == "reply"

    def test_schedule_verb(self):
        """Test schedule verb detection."""
        intent = parse_intent("Schedule a meeting with the team")
        assert intent.verb == "schedule"

        intent = parse_intent("Book a meeting tomorrow")
        assert intent.verb == "schedule"

        intent = parse_intent("Set up a meeting with Alice")
        assert intent.verb == "schedule"

    def test_create_verb(self):
        """Test create verb detection."""
        intent = parse_intent("Create a new page for the project")
        assert intent.verb == "create"

        intent = parse_intent("Make a document")
        assert intent.verb == "create"

    def test_update_verb(self):
        """Test update verb detection."""
        intent = parse_intent("Update the status field")
        assert intent.verb == "update"

        intent = parse_intent("Edit the document")
        assert intent.verb == "update"

    def test_delete_verb(self):
        """Test delete verb detection."""
        intent = parse_intent("Delete old messages")
        assert intent.verb == "delete"

        intent = parse_intent("Remove the file")
        assert intent.verb == "delete"

    def test_find_verb(self):
        """Test find verb detection."""
        intent = parse_intent("Find messages from Alice")
        assert intent.verb == "find"

        intent = parse_intent("Search for the contract")
        assert intent.verb == "find"

        intent = parse_intent("Look for budget spreadsheet")
        assert intent.verb == "find"

    def test_list_verb(self):
        """Test list verb detection."""
        intent = parse_intent("List all contacts")
        assert intent.verb == "list"

        intent = parse_intent("Show all messages")
        assert intent.verb == "list"

    def test_verb_priority(self):
        """Test verb priority (specific over general)."""
        # Reply is more specific than message
        intent = parse_intent("Reply to the message from Alice")
        assert intent.verb == "reply"

        # Forward is more specific than email
        intent = parse_intent("Forward the email to Bob")
        assert intent.verb == "forward"

    def test_unknown_verb(self):
        """Test unknown verb."""
        intent = parse_intent("Do something random")
        assert intent.verb == "unknown"


class TestTargetExtraction:
    """Test target extraction from commands."""

    def test_email_addresses(self):
        """Test email address extraction."""
        intent = parse_intent("Email alice@example.com about the project")
        assert "alice@example.com" in intent.targets

        intent = parse_intent("Send to bob@company.com and charlie@company.com")
        assert "bob@company.com" in intent.targets
        assert "charlie@company.com" in intent.targets

    def test_person_names(self):
        """Test person name extraction."""
        intent = parse_intent("Message Alice about the meeting")
        assert "Alice" in intent.targets

        intent = parse_intent("Send to Bob Smith")
        assert "Bob Smith" in intent.targets

        intent = parse_intent("Forward to Alice Johnson")
        assert "Alice Johnson" in intent.targets

    def test_team_names(self):
        """Test team name extraction."""
        intent = parse_intent("Message the Engineering team")
        assert "Engineering team" in intent.targets

        intent = parse_intent("Send to the Legal team")
        assert "Legal team" in intent.targets

    def test_channel_names(self):
        """Test channel name extraction."""
        intent = parse_intent("Post in #general channel")
        assert "general" in intent.targets

        intent = parse_intent("Send to the Marketing channel")
        assert "Marketing" in intent.targets

    def test_from_pattern(self):
        """Test 'from' pattern extraction."""
        intent = parse_intent("Find messages from Alice")
        assert "Alice" in intent.targets

    def test_possessive_pattern(self):
        """Test possessive pattern extraction."""
        intent = parse_intent("Reply to Bob's message")
        assert "Bob" in intent.targets

    def test_deduplication(self):
        """Test target deduplication."""
        intent = parse_intent("Email Alice and message Alice")
        # Should only have Alice once
        alice_count = sum(1 for t in intent.targets if t.lower() == "alice")
        assert alice_count == 1


class TestArtifactExtraction:
    """Test artifact extraction from commands."""

    def test_quoted_strings(self):
        """Test quoted string extraction."""
        intent = parse_intent('Email "Q4 Budget Report" to Alice')
        assert "Q4 Budget Report" in intent.artifacts

        intent = parse_intent('Send "the meeting notes" to Bob')
        assert "the meeting notes" in intent.artifacts

    def test_the_phrases(self):
        """Test 'the [phrase]' extraction."""
        intent = parse_intent("Forward the contract to Legal")
        assert "contract" in intent.artifacts

        intent = parse_intent("Send the budget spreadsheet")
        assert "budget spreadsheet" in intent.artifacts

    def test_about_phrases(self):
        """Test 'about [topic]' extraction."""
        intent = parse_intent("Find messages about planning")
        assert "planning" in intent.artifacts

        intent = parse_intent("Search about the project status")
        assert "project status" in intent.artifacts

    def test_artifact_length_limit(self):
        """Test artifact length limits."""
        long_phrase = "a" * 60
        intent = parse_intent(f"Send the {long_phrase}")
        # Should not include overly long phrases
        assert not any(len(a) > 50 for a in intent.artifacts)

    def test_team_channel_filtering(self):
        """Test that team/channel references are filtered out."""
        intent = parse_intent("Send to the Engineering team")
        # "Engineering" should be in targets, not artifacts
        assert "Engineering team" in intent.targets
        assert "Engineering" not in intent.artifacts


class TestConstraintExtraction:
    """Test constraint extraction from commands."""

    def test_source_constraint(self):
        """Test source connector extraction."""
        intent = parse_intent("Find messages in Teams")
        assert intent.constraints.get("source") == "teams"

        intent = parse_intent("Search Slack for files")
        assert intent.constraints.get("source") == "slack"

        intent = parse_intent("Get outlook emails")
        assert intent.constraints.get("source") == "outlook"

        intent = parse_intent("Find Gmail messages")
        assert intent.constraints.get("source") == "gmail"

    def test_time_constraint(self):
        """Test time constraint extraction."""
        intent = parse_intent("Find messages from today")
        assert intent.constraints.get("time") == "today"

        intent = parse_intent("Get emails from yesterday")
        assert intent.constraints.get("time") == "yesterday"

        intent = parse_intent("Find files from this week")
        assert intent.constraints.get("time") == "this_week"

        intent = parse_intent("Search last month")
        assert intent.constraints.get("time") == "last_month"

    def test_label_constraint(self):
        """Test label/tag extraction."""
        intent = parse_intent("Find messages with label urgent")
        assert intent.constraints.get("label") == "urgent"

        intent = parse_intent('Search with tag "important"')
        assert intent.constraints.get("label") == "important"

    def test_folder_constraint(self):
        """Test folder extraction."""
        intent = parse_intent("Find files in the Archive folder")
        assert intent.constraints.get("folder") == "Archive"

        intent = parse_intent("Search in Budget Reports folder")
        assert intent.constraints.get("folder") == "Budget Reports"


class TestIntentValidation:
    """Test intent validation."""

    def test_valid_email_intent(self):
        """Test valid email intent."""
        intent = parse_intent("Email alice@example.com about the meeting")
        is_valid, error = validate_intent(intent)
        assert is_valid
        assert error is None

    def test_invalid_email_no_target(self):
        """Test email without target."""
        intent = Intent(verb="email", targets=[], original_command="Email about meeting")
        is_valid, error = validate_intent(intent)
        assert not is_valid
        assert "target" in error.lower()

    def test_invalid_unknown_verb(self):
        """Test unknown verb."""
        intent = Intent(verb="unknown", original_command="Do something")
        is_valid, error = validate_intent(intent)
        assert not is_valid
        assert "verb" in error.lower()

    def test_valid_find_intent(self):
        """Test valid find intent."""
        intent = parse_intent("Find messages from Alice")
        is_valid, error = validate_intent(intent)
        assert is_valid

    def test_invalid_message_no_target(self):
        """Test message without target."""
        intent = Intent(verb="message", targets=[], original_command="Message")
        is_valid, error = validate_intent(intent)
        assert not is_valid
        assert "target" in error.lower()


class TestComplexCommands:
    """Test complex real-world commands."""

    def test_email_with_artifact(self):
        """Test email command with artifact."""
        intent = parse_intent('Email the "Q4 Budget" spreadsheet to alice@example.com')
        assert intent.verb == "email"
        assert "alice@example.com" in intent.targets
        assert "Q4 Budget" in intent.artifacts

    def test_forward_to_multiple(self):
        """Test forward to multiple recipients."""
        intent = parse_intent("Forward the contract to alice@example.com and bob@example.com")
        assert intent.verb == "forward"
        assert "alice@example.com" in intent.targets
        assert "bob@example.com" in intent.targets
        assert "contract" in intent.artifacts

    def test_find_with_constraints(self):
        """Test find with multiple constraints."""
        intent = parse_intent("Find messages from Alice in Teams about planning from yesterday")
        assert intent.verb == "find"
        assert "Alice" in intent.targets
        assert "planning" in intent.artifacts
        assert intent.constraints.get("source") == "teams"
        assert intent.constraints.get("time") == "yesterday"

    def test_schedule_meeting(self):
        """Test schedule meeting command."""
        intent = parse_intent("Schedule a meeting with Alice and Bob tomorrow at 2pm")
        assert intent.verb == "schedule"
        assert "Alice" in intent.targets
        assert "Bob" in intent.targets

    def test_reply_with_quoted_text(self):
        """Test reply with quoted message."""
        intent = parse_intent('Reply to Bob\'s message with "Sounds good, thanks!"')
        assert intent.verb == "reply"
        assert "Bob" in intent.targets
        assert "Sounds good, thanks!" in intent.artifacts
