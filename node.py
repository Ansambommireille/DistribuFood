import os
import glob
import grpc
from concurrent import futures
import storage_pb2
import storage_pb2_grpc

class StorageNodeServicer(storage_pb2_grpc.StorageNodeServicer):
    def __init__(self, storage_dir, max_storage_mb=250):
        self.storage_dir = storage_dir
        self.max_storage = max_storage_mb * 1024 * 1024  # 250 MB
        os.makedirs(storage_dir, exist_ok=True)

    def _used_space(self):
        return sum(os.path.getsize(f) for f in glob.glob(f"{self.storage_dir}/*") if os.path.isfile(f))

    def StoreBlock(self, request, context):
        if self._used_space() + len(request.data) > self.max_storage:
            return storage_pb2.StoreResponse(success=False, message="No space left")
        path = os.path.join(self.storage_dir, request.block_id)
        with open(path, "wb") as f:
            f.write(request.data)
        return storage_pb2.StoreResponse(success=True, message="OK")

    def GetBlock(self, request, context):
        path = os.path.join(self.storage_dir, request.block_id)
        if not os.path.exists(path):
            return storage_pb2.GetResponse(success=False, message="Not found", data=b"")
        with open(path, "rb") as f:
            data = f.read()
        return storage_pb2.GetResponse(success=True, data=data, message="OK")

    def DeleteBlock(self, request, context):
        path = os.path.join(self.storage_dir, request.block_id)
        if os.path.exists(path):
            os.remove(path)
            return storage_pb2.DeleteResponse(success=True, message="Deleted")
        return storage_pb2.DeleteResponse(success=False, message="Not found")

    def GetAvailableSpace(self, request, context):
        return storage_pb2.SpaceResponse(available=self.max_storage - self._used_space())

def serve(port):
    storage_dir = f"nodes_storage/storage_{port}"
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    storage_pb2_grpc.add_StorageNodeServicer_to_server(
        StorageNodeServicer(storage_dir), server
    )
    server.add_insecure_port(f"[::]:{port}")
    print(f"Storage node started → port {port} | folder: {storage_dir}")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    serve(args.port)