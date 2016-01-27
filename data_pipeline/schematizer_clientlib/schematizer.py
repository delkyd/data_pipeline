# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import simplejson

from data_pipeline.config import get_config
from data_pipeline.helpers.singleton import Singleton
from data_pipeline.schematizer_clientlib.models.avro_schema import _AvroSchema
from data_pipeline.schematizer_clientlib.models.refresh import _Refresh
from data_pipeline.schematizer_clientlib.models.source import _Source
from data_pipeline.schematizer_clientlib.models.topic import _Topic


class SchematizerClient(object):
    """A client that interacts with Schematizer APIs.  It has built-in caching
    feature which caches avro schemas, topics, and etc.  Right now the cache is
    only in memory (TODO(DATAPIPE-162|joshszep): Implement persistent caching).

    It caches schemas, topics, and sources separately instead of caching nested
    objects to avoid storing duplicate data repeatedly.
    """

    __metaclass__ = Singleton

    def __init__(self):
        self._client = get_config().schematizer_client  # swaggerpy client
        self._schema_cache = {}
        self._topic_cache = {}
        self._source_cache = {}
        self._avro_schema_cache = {}

    def get_schema_by_id(self, schema_id):
        """Get the avro schema of given schema id.

        Args:
            schema_id (int): The id of requested avro schema.

        Returns:
            (data_pipeline.schematizer_clientlib.models.avro_schema.AvroSchema):
                The requested avro Schema.
        """
        return self._get_schema_by_id(schema_id).to_result()

    def _get_schema_by_id(self, schema_id):
        cached_schema = self._schema_cache.get(schema_id)
        if cached_schema:
            _schema = _AvroSchema.from_cache_value(cached_schema)
            _schema.topic = self._get_topic_by_name(cached_schema['topic_name'])
        else:
            response = self._call_api(
                api=self._client.schemas.get_schema_by_id,
                params={'schema_id': schema_id}
            )
            _schema = _AvroSchema.from_response(response)
            self._update_cache_by_schema(_schema)
        return _schema

    def _make_avro_schema_key(self, schema_json):
        return simplejson.dumps(schema_json, sort_keys=True)

    def get_schema_by_schema_json(self, schema_json):
        """ Get schema object if one exists for a given avro schema.
        If not, return None.

        Args:
            schema_json (dict or list): Python object representation of the
                avro schema json.

        Returns:
            (data_pipeline.schematizer_clientlib.models.avro_schema.AvroSchema):
                Avro Schema object.
        """
        cached_schema = self._avro_schema_cache.get(
            self._make_avro_schema_key(schema_json)
        )
        if cached_schema:
            _schema = _AvroSchema.from_cache_value(cached_schema)
            _schema.topic = self._get_topic_by_name(cached_schema['topic_name'])
            return _schema.to_result()
        else:
            # TODO(DATAPIPE-608|askatti): Add schematizer endpoint to return
            # Schema object given a schema_json
            return None

    def get_topic_by_name(self, topic_name):
        """Get the topic of given topic name.

        Args:
            topic_name (str): The name of requested topic.

        Returns:
            (data_pipeline.schematizer_clientlib.models.topic.Topic):
                The requested topic.
        """
        return self._get_topic_by_name(topic_name).to_result()

    def _get_topic_by_name(self, topic_name):
        cached_topic = self._topic_cache.get(topic_name)
        if cached_topic:
            _topic = _Topic.from_cache_value(cached_topic)
            _topic.source = self._get_source_by_id(cached_topic['source_id'])
        else:
            response = self._call_api(
                api=self._client.topics.get_topic_by_topic_name,
                params={'topic_name': topic_name}
            )
            _topic = _Topic.from_response(response)
            self._update_cache_by_topic(_topic)
        return _topic

    def get_source_by_id(self, source_id):
        """Get the schema source of given source id.

        Args:
            source_id (int): The id of the source.

        Returns:
            (data_pipeline.schematizer_clientlib.models.topic.Source):
                The requested schema source.
        """
        return self._get_source_by_id(source_id).to_result()

    def _get_source_by_id(self, source_id):
        cached_source = self._source_cache.get(source_id)
        if cached_source:
            _source = _Source.from_cache_value(cached_source)
        else:
            response = self._call_api(
                api=self._client.sources.get_source_by_id,
                params={'source_id': source_id}
            )
            _source = _Source.from_response(response)
            self._update_cache_by_source(_source)
        return _source

    def get_sources_by_namespace(self, namespace_name):
        """Get the list of sources in the specified namespace.

        Args:
            namespace_name (str): namespace name to look up

        Returns:
            (List[data_pipeline.schematizer_clientlib.models.source.Source]):
                The list of schemas sources in the given namespace.
        """
        response = self._call_api(
            api=self._client.namespaces.list_sources_by_namespace,
            params={'namespace': namespace_name}
        )
        result = []
        for resp_item in response:
            _source = _Source.from_response(resp_item)
            result.append(_source.to_result())
            self._update_cache_by_source(_source)
        return result

    def get_topics_by_source_id(self, source_id):
        """Get the list of topics of specified source id.

        Args:
            source_id (int): The id of the source to look up

        Returns:
            (List[data_pipeline.schematizer_clientlib.models.topic.Topic]):
                The list of topics of given source.
        """
        response = self._call_api(
            api=self._client.sources.list_topics_by_source_id,
            params={'source_id': source_id}
        )
        result = []
        for resp_item in response:
            _topic = _Topic.from_response(resp_item)
            result.append(_topic.to_result())
            self._update_cache_by_topic(_topic)
        return result

    def get_latest_schema_by_topic_name(self, topic_name):
        """Get the latest enabled schema of given topic.

        Args:
            topic_name (str): The topic name of which

        Returns:
            (data_pipeline.schematizer_clientlib.models.avro_schema.AvroSchema):
                The latest enabled avro schema of given topic.  It returns None
                if no such avro schema can be found.
        """
        response = self._call_api(
            api=self._client.topics.get_latest_schema_by_topic_name,
            params={'topic_name': topic_name}
        )
        _schema = _AvroSchema.from_response(response)
        self._update_cache_by_schema(_schema)
        return _schema.to_result()

    def register_schema(
        self,
        namespace,
        source,
        schema_str,
        source_owner_email,
        contains_pii,
        base_schema_id=None
    ):
        """ Register a new schema and return newly created schema object.

        Args:
            namespace (str): The namespace the new schema is registered to.
            source (str): The source the new schema is registered to.
            schema_str (str): String representation of the avro schema.
            source_owner_email (str): The owner email of the given source.
            contains_pii (bool): Indicates if the schema being registered has
                at least one field that can potentially contain PII.
                See http://y/pii for help identifying what is or is not PII.
            base_schema_id (Optional[int]): The id of the original schema which
                the new schema was changed based on

        Returns:
            (data_pipeline.schematizer_clientlib.models.avro_schema.AvroSchema):
                The newly created avro Schema.
        """
        post_body = {
            'schema': schema_str,
            'namespace': namespace,
            'source': source,
            'source_owner_email': source_owner_email,
            'contains_pii': contains_pii,
        }
        if base_schema_id:
            post_body['base_schema_id'] = base_schema_id
        response = self._call_api(
            api=self._client.schemas.register_schema,
            post_body=post_body
        )

        _schema = _AvroSchema.from_response(response)
        self._update_cache_by_schema(_schema)
        return _schema.to_result()

    def register_schema_from_schema_json(
        self,
        namespace,
        source,
        schema_json,
        source_owner_email,
        contains_pii,
        base_schema_id=None
    ):
        """ Register a new schema and return newly created schema object.

        Args:
            namespace (str): The namespace the new schema is registered to.
            source (str): The source the new schema is registered to.
            schema_json (dict or list): Python object representation of the
                avro schema json.
            source_owner_email (str): The owner email of the given source.
            contains_pii (bool): Indicates if the schema being registered has
                at least one field that can potentially contain PII.
                See http://y/pii for help identifying what is or is not PII.
            base_schema_id (Optional[int]): The id of the original schema which
                the new schema was changed based on

        Returns:
            (data_pipeline.schematizer_clientlib.models.avro_schema.AvroSchema):
                The newly created avro Schema.
        """
        return self.register_schema(
            namespace=namespace,
            source=source,
            schema_str=simplejson.dumps(schema_json),
            source_owner_email=source_owner_email,
            contains_pii=contains_pii,
            base_schema_id=base_schema_id
        )

    def register_schema_from_mysql_stmts(
        self,
        namespace,
        source,
        source_owner_email,
        contains_pii,
        new_create_table_stmt,
        old_create_table_stmt=None,
        alter_table_stmt=None,
    ):
        """ Register schema based on mysql statements and return newly created
        schema.

        Args:
            namespace (str): The namespace the new schema is registered to.
            source (str): The source the new schema is registered to.
            source_owner_email (str): The owner email of the given source.
            contains_pii (bool): The flag indicating if schema contains pii.
            new_create_table_stmt (str): the mysql statement of creating new table.
            old_create_table_stmt (Optional[str]): the mysql statement of
                creating old table.
            alter_table_stmt (Optional[str]): the mysql statement of altering
                table schema.

        Returns:
            (data_pipeline.schematizer_clientlib.models.avro_schema.AvroSchema):
                The newly created avro Schema.
        """
        post_body = {
            'namespace': namespace,
            'source': source,
            'new_create_table_stmt': new_create_table_stmt,
            'source_owner_email': source_owner_email,
            'contains_pii': contains_pii
        }
        if old_create_table_stmt:
            post_body['old_create_table_stmt'] = old_create_table_stmt
        if alter_table_stmt:
            post_body['alter_table_stmt'] = alter_table_stmt
        response = self._call_api(
            api=self._client.schemas.register_schema_from_mysql_stmts,
            post_body=post_body
        )

        _schema = _AvroSchema.from_response(response)
        self._update_cache_by_schema(_schema)
        return _schema.to_result()

    def get_topics_by_criteria(
        self,
        namespace_name=None,
        source_name=None,
        created_after=None
    ):
        """Get all the topics that match specified criteria.  If no criterion
        is specified, it returns all the topics.

        Args:
            namespace_name (Optional[str]): namespace the topics belong to
            source_name (Optional[str]): name of the source topics belong to
            created_after (Optional[int]): Epoch timestamp the topics should be
                created after.  The topics created at the same timestamp are
                also included.

        Returns:
            (List[data_pipeline.schematizer_clientlib.models.topic.Topic]):
                list of topics that match given criteria.
        """
        response = self._call_api(
            api=self._client.topics.get_topics_by_criteria,
            params={
                'namespace': namespace_name,
                'source': source_name,
                'created_after': created_after
            }
        )
        result = []
        for resp_item in response:
            _topic = _Topic.from_response(resp_item)
            result.append(_topic.to_result())
            self._update_cache_by_topic(_topic)
        return result

    def get_refreshes_by_criteria(
        self,
        namespace_name=None,
        status=None,
        created_after=None
    ):
        """Get all the refreshes that match the specified criteria. If no
        criterion is specified, it returns all refreshes.

        Args:
            namespace_name (Optional[str]): namespace the topics belong to.
            status (Optional[str]): The status associated with the refresh.
            created_after (Optional[int]): Epoch timestamp the refreshes should
                be created after. The refreshes created at the same timestamp
                are also included.

        Returns:
            (List[data_pipeline.schematizer_clientlib.models.refresh.Refresh]):
                list of refreshes that match the given criteria.
        """
        response = self._call_api(
            api=self._client.refreshes.get_refreshes_by_criteria,
            params={
                'namespace': namespace_name,
                'status': status,
                'created_after': created_after
            }
        )
        return [get_refresh_result_from_response(resp) for resp in response]

    def create_refresh(
        self,
        source_id,
        offset,
        batch_size,
        priority,
        filter_condition=None,
        avg_rows_per_second_cap=None
    ):
        """Register a refresh and returns the newly created refresh object.

        Args:
            source_id (int): The id of the source of the refresh.
            offset (int): The last known offset that has been refreshed.
            batch_size (int): The number of rows to be refreshed per batch.
            priority (int): The priority of the refresh (1-100)
            filter_condition (str): The filter condition associated with
             the refresh.
            avg_rows_per_second_cap (int): Throughput throttle of the refresh.

        Returns:
            (data_pipeline.schematizer_clientlib.models.refresh.Refresh):
                The newly created Refresh.
        """
        post_body = {
            'offset': offset,
            'batch_size': batch_size,
            'priority': priority,
        }
        if filter_condition:
            post_body['filter_condition'] = filter_condition
        if avg_rows_per_second_cap is not None:
            post_body['avg_rows_per_second_cap'] = avg_rows_per_second_cap
        response = self._call_api(
            api=self._client.sources.create_refresh,
            params={'source_id': source_id, 'body': post_body}
        )
        return get_refresh_result_from_response(response)

    def update_refresh(self, refresh_id, status, offset):
        """Update the status of the refresh with specified refresh_id.

        Args:
            refresh_id (int): The id of the refresh being updated.
            status (str): New status of the refresh.
            offset (int): Last known offset that has been refreshed.

        Returns:
            (data_pipeline.schematizer_clientlib.models.refresh.Refresh):
                The updated Refresh.
        """
        post_body = {
            'status': status,
            'offset': offset
        }
        response = self._call_api(
            api=self._client.refreshes.update_refresh,
            params={'refresh_id': refresh_id, 'body': post_body}
        )
        return get_refresh_result_from_response(response)

    def get_refreshes_by_namespace(self, namespace_name):
        """"Get the list of refreshes in the specified namespace.

        Args:
            namespace_name (str): namespace name to look up.

        Returns:
            (List[data_pipeline.schematizer_clientlib.models.refresh.Refresh]):
                The list of refreshes in the given namespace.
        """
        response = self._call_api(
            api=self._client.namespaces.list_refreshes_by_namespace,
            params={'namespace': namespace_name}
        )
        return [get_refresh_result_from_response(resp) for resp in response]

    def get_refresh_by_id(self, refresh_id):
        """Get the refresh associated with specified refresh_id.

        Args:
            refresh_id (int): The id of the refresh.

        Returns:
            (data_pipeline.schematizer_clientlib.models.refresh.Refresh):
                The refresh with the given refresh_id.
        """
        response = self._call_api(
            api=self._client.refreshes.get_refresh_by_id,
            params={'refresh_id': str(refresh_id)}
        )
        return get_refresh_result_from_response(response)

    def _call_api(self, api, params=None, post_body=None):
        # TODO(DATAPIPE-207|joshszep): Include retry strategy support
        request_params = {'body': post_body} if post_body else params or {}
        request = api(**request_params)
        response = request.result()
        return response

    def _update_cache_by_schema(self, new_schema):
        self._schema_cache[new_schema.schema_id] = new_schema.to_cache_value()
        self._update_cache_by_topic(new_schema.topic)
        self._avro_schema_cache[
            self._make_avro_schema_key(new_schema.schema_json)
        ] = new_schema.to_cache_value()

    def _update_cache_by_topic(self, new_topic):
        self._topic_cache[new_topic.name] = new_topic.to_cache_value()
        self._update_cache_by_source(new_topic.source)

    def _update_cache_by_source(self, new_source):
        self._source_cache[new_source.source_id] = new_source.to_cache_value()


def get_refresh_result_from_response(response):
    _refresh = _Refresh.from_response(response)
    return _refresh.to_result()


def get_schematizer():
    return SchematizerClient()
