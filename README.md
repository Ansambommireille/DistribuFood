# DistribuFood
A Distributed platform designed to ease food ordering
Introduction
DistribuFood is a robust and scalable distributed online food ordering system designed to address the challenges faced by traditional centralized platforms. It leverages cloud computing and distributed system principles to provide reliable, real-time food ordering, menu management, and payment processing services across multiple cooperating servers. The platform aims to maintain seamless service availability, data consistency, and fault tolerance, delivering an efficient user experience during peak demand periods and failure scenarios.

Project Objective
The goal of DistribuFood is to build a distributed microservices-based platform that supports concurrent users and restaurants, allowing real-time menu updates, order placement, secure payments, and order tracking. It enhances scalability and reliability by distributing the workload across cooperative servers while ensuring consistent and fault-tolerant data synchronization.

Problem Statement
Traditional online food ordering systems encounter bottlenecks under heavy load due to centralized architectures. These systems often suffer from single points of failure, leading to downtime and inconsistent data during critical processes like order placement and payment. Scalability issues compromise user experience, especially during high-traffic intervals.

Problem Being Solved
DistribuFood solves these problems by distributing backend services across multiple servers, eliminating single points of failure, and improving scalability. It maintains consistency of order and payment data through distributed consensus protocols, ensures fault tolerance via data replication, and balances load dynamically to optimize response times.

System Design and Architecture
DistribuFood adopts a microservices architecture deployed across a cloud infrastructure with the following components:

User Service: Manages user accounts, authentication, and profile data.

Restaurant Service: Enables restaurants to manage menus and availability in real-time.

Order Service: Coordinates order placement, updating, and concurrency control with distributed transactions.

Payment Service: Handles secure payment processing and transaction state synchronization.

API Gateway: Acts as a unified entry point, routing requests and balancing load across services.

Message Broker: Facilitates asynchronous event-driven communication between microservices to provide eventual consistency and fault tolerance.

Distributed databases like Apache Cassandra or MongoDB clusters provide horizontally scalable and replicated data storage. Consensus mechanisms such as Raft ensure ordered and reliable updates for critical operations.

Technologies Used
Backend frameworks: Python (Flask or FastAPI), Node.js

Distributed databases: Apache Cassandra, MongoDB

Messaging: Apache Kafka, RabbitMQ

Containerization: Docker

Orchestration: Kubernetes

Cloud platforms: AWS, Azure, Google Cloud

API Gateway: Nginx or cloud-native solutions

Authentication: OAuth 2.0, JSON Web Tokens (JWT)

Distributed Systems Principles
Scalability: Horizontal scaling of stateless microservices and distributed databases ensures the platform can handle growing loads.

Fault Tolerance: Data replication, consensus algorithms, and message queues provide resilience against node failures.

Consistency: Using distributed consensus to synchronize order and payment states guarantees data integrity.

Load Balancing: API Gateway and load balancers distribute client requests evenly to optimize resource utilization.

Decoupling and Asynchronicity: Ensures microservices operate independently, reducing cascading failures and improving maintenance.
