from __future__ import absolute_import

import subprocess
import uuid
from collections import defaultdict
from contextlib import contextmanager

from confluent_kafka import Producer

from sentry.eventstream.kafka.consumer import SynchronizedConsumer


@contextmanager
def create_topic(partitions=1, replication_factor=1):
    command = ['docker', 'exec', 'kafka', 'kafka-topics'] + ['--zookeeper', 'zookeeper:2181']
    topic = 'test-{}'.format(uuid.uuid1().hex)
    subprocess.check_call(command + [
        '--create',
        '--topic', topic,
        '--partitions', '{}'.format(partitions),
        '--replication-factor', '{}'.format(replication_factor),
    ])
    try:
        yield topic
    finally:
        subprocess.check_call(command + [
            '--delete',
            '--topic', topic,
        ])


def test_consumer_start_from_partition_start():
    synchronize_commit_group = 'consumer-{}'.format(uuid.uuid1().hex)

    messages_delivered = defaultdict(list)

    def record_message_delivered(error, message):
        assert error is None
        messages_delivered[message.topic()].append(message)

    producer = Producer({
        'bootstrap.servers': 'localhost:9092',
        'on_delivery': record_message_delivered,
    })

    with create_topic() as topic, create_topic() as commit_log_topic:
        # Create the synchronized consumer.
        consumer = SynchronizedConsumer(
            bootstrap_servers='localhost:9092',
            topics=[topic],
            consumer_group='consumer-{}'.format(uuid.uuid1().hex),
            commit_log_topic=commit_log_topic,
            synchronize_commit_group=synchronize_commit_group,
        )
        consumer.start()

        # TODO: Make sure that all partitions are paused on assignment.

        # Produce some messages into the topic.
        for i in range(3):
            producer.produce(topic, '{}'.format(i).encode('utf8'))

        assert producer.flush(5) == 0, 'producer did not successfully flush queue'

        # TODO: Make sure that all partitions remain paused.

        # Make sure that there are no messages ready to consume.
        assert consumer.poll(1) is None

        # Move the committed offset forward for our synchronizing group.
        message = messages_delivered[topic][0]
        producer.produce(
            commit_log_topic,
            key='{}:{}:{}'.format(
                message.topic(),
                message.partition(),
                synchronize_commit_group,
            ).encode('utf8'),
            value='{}'.format(
                message.offset() + 1,
            ).encode('utf8'),
        )

        assert producer.flush(5) == 0, 'producer did not successfully flush queue'

        # We should have received a single message.
        # TODO: Can we also assert that the position is unpaused?)
        for i in xrange(5):
            message = consumer.poll(1)
            if message is not None:
                break

        assert message is not None, 'no message received'

        expected_message = messages_delivered[topic][0]
        assert message.topic() == expected_message.topic()
        assert message.partition() == expected_message.partition()
        assert message.offset() == expected_message.offset()

        # We should not be able to continue reading into the topic.
        # TODO: Can we assert that the position is paused?
        assert consumer.poll(1) is None


def test_consumer_start_from_committed_offset():
    raise NotImplementedError


def test_consumer_rebalance_from_partition_start():
    raise NotImplementedError


def test_consumer_rebalance_from_committed_offset():
    raise NotImplementedError


def test_consumer_rebalance_from_uncommitted_offset():
    raise NotImplementedError
