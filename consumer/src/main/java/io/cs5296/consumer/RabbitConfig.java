package io.cs5296.consumer;

import org.springframework.amqp.core.Queue;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitConfig {

    /**
     * Queue name is injected from the environment so the same image can be
     * reused for both the HPA and KEDA experiment groups with different queues.
     */
    @Value("${consumer.queue}")
    private String queueName;

    @Bean
    public Queue workQueue() {
        return new Queue(queueName, true);
    }
}
