{% macro validate_pluto_inputs() %}
{% if execute %}
  {# Invalidate any previous completion before starting this invocation. #}
  {% do run_query('CREATE SCHEMA IF NOT EXISTS pluto_execution') %}
  {% do run_query("CREATE OR REPLACE TABLE pluto_execution.receipt AS SELECT '" ~ invocation_id ~ "'::VARCHAR AS invocation_id, 'running'::VARCHAR AS status, NULL::VARCHAR AS input_id, NULL::VARCHAR AS descriptor_sha256") %}
  {% do run_query('LOAD spatial') %}
  {% set database = var('input_database', 'prepared') %}
  {% set escaped = database | replace("'", "''") %}
  {% set attached = run_query("SELECT readonly FROM duckdb_databases() WHERE database_name='" ~ escaped ~ "'") %}
  {% if attached.rows | length != 1 %}
    {{ exceptions.raise_compiler_error('PLUTO input contract: attach the prepared input database as ' ~ database ~ '.') }}
  {% elif not attached.rows[0][0] %}
    {{ exceptions.raise_compiler_error('PLUTO input contract: ' ~ database ~ ' must be attached read_only; use a separate writable output database.') }}
  {% endif %}
  {% set identity_table = run_query("SELECT count(*) FROM information_schema.tables WHERE table_catalog='" ~ escaped ~ "' AND table_schema='preparation' AND table_name='identity'") %}
  {% if identity_table.rows[0][0] != 1 %}
    {{ exceptions.raise_compiler_error('PLUTO input contract: missing preparation.identity publication receipt.') }}
  {% endif %}
  {% set identity_relation = adapter.quote(database) ~ '.preparation.identity' %}
  {% set identity = run_query('SELECT input_id, descriptor_sha256 FROM ' ~ identity_relation) %}
  {% if identity.rows | length != 1 or not identity.rows[0][0] or not identity.rows[0][1] or identity.rows[0][1] | length != 64 %}
    {{ exceptions.raise_compiler_error('PLUTO input contract: preparation.identity must contain one publication ID and SHA256 descriptor.') }}
  {% endif %}
  {% do run_query('UPDATE pluto_execution.receipt SET input_id=(SELECT input_id FROM ' ~ identity_relation ~ '), descriptor_sha256=(SELECT descriptor_sha256 FROM ' ~ identity_relation ~ ')') %}
  {% set columns = run_query("SELECT table_name,column_name,data_type FROM information_schema.columns WHERE table_catalog='" ~ escaped ~ "' AND table_schema='sources' ORDER BY table_name,ordinal_position") %}
  {% set actual = {} %}
  {% for table, column, dtype in columns.rows %}
    {% if table not in actual %}{% do actual.update({table: {}}) %}{% endif %}
    {% do actual[table].update({column: dtype | upper | replace(' ', '')}) %}
  {% endfor %}
  {% set failures = [] %}
  {% for node in graph.sources.values() if node.source_name == 'pluto_inputs' %}
    {% if node.name not in actual %}
      {% do failures.append('missing table sources.' ~ node.name) %}
    {% else %}
      {% for name, column in node.columns.items() %}
        {% if name not in actual[node.name] %}
          {% do failures.append('missing column sources.' ~ node.name ~ '.' ~ name) %}
        {% elif actual[node.name][name] != column.data_type | upper | replace(' ', '') %}
          {% do failures.append('type mismatch sources.' ~ node.name ~ '.' ~ name ~ ': expected ' ~ column.data_type ~ ', found ' ~ actual[node.name][name]) %}
        {% endif %}
      {% endfor %}
      {% for name in actual[node.name] if name not in node.columns %}
        {% do failures.append('unexpected column sources.' ~ node.name ~ '.' ~ name) %}
      {% endfor %}
      {% if actual[node.name].keys() | list != node.columns.keys() | list %}
        {% do failures.append('column order mismatch sources.' ~ node.name) %}
      {% endif %}
    {% endif %}
  {% endfor %}
  {% if failures %}
    {{ exceptions.raise_compiler_error('PLUTO input contract failed:\n- ' ~ failures[:20] | join('\n- ')) }}
  {% endif %}
{% endif %}
SELECT 1 AS validated_pluto_input_contract
{% endmacro %}

{% macro complete_pluto_execution(results) %}
{% if execute %}
  {% set expected = [] %}
  {% for node in graph.nodes.values() if node.resource_type == 'model' and node.package_name == project_name %}
    {% do expected.append(node.unique_id) %}
  {% endfor %}
  {% set successful = [] %}
  {% for result in results if result.node.resource_type == 'model' and result.status == 'success' %}
    {% do successful.append(result.node.unique_id) %}
  {% endfor %}
  {% set missing = [] %}
  {% for model in expected if model not in successful %}{% do missing.append(model) %}{% endfor %}
  {% set failed = [] %}
  {% for result in results if result.status not in ['success', 'pass', 'warn'] %}
    {% do failed.append(result.node.unique_id) %}
  {% endfor %}
  {% set status = 'complete' if expected | length == 38 and not missing and not failed else 'incomplete' %}
  UPDATE pluto_execution.receipt SET status='{{ status }}'
  WHERE invocation_id='{{ invocation_id }}'
{% else %}
  SELECT 1
{% endif %}
{% endmacro %}
