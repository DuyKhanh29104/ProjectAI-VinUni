import {
  useEffect,
  useRef,
  useState,
  type ImgHTMLAttributes,
} from "react";
import { labelGuardianApiV1 } from "../api/labelGuardianApi";
import { isSupabaseAuthEnabled } from "../auth/supabase";

interface AssetState {
  source: string;
  error: string;
}

export function useAuthenticatedAssetUrl(path?: string, enabled = true): AssetState {
  const [state, setState] = useState<AssetState>({ source: "", error: "" });

  useEffect(() => {
    if (!path || !enabled) {
      setState({ source: "", error: "" });
      return;
    }
    if (!isSupabaseAuthEnabled()) {
      setState({ source: labelGuardianApiV1.resolveAssetUrl(path), error: "" });
      return;
    }

    const controller = new AbortController();
    let objectUrl = "";
    setState({ source: "", error: "" });
    void labelGuardianApiV1.fetchAsset(path, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setState({ source: objectUrl, error: "" });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          source: "",
          error: error instanceof Error ? error.message : "Không thể tải ảnh.",
        });
      });

    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [enabled, path]);

  return state;
}

export function AuthenticatedImage({
  sourcePath,
  onAssetError,
  ...props
}: ImgHTMLAttributes<HTMLImageElement> & {
  sourcePath?: string;
  onAssetError?: (message: string) => void;
}) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [shouldLoad, setShouldLoad] = useState(props.loading !== "lazy");

  useEffect(() => {
    if (props.loading !== "lazy" || shouldLoad) return;
    const element = imageRef.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setShouldLoad(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShouldLoad(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [props.loading, shouldLoad]);

  const asset = useAuthenticatedAssetUrl(sourcePath, shouldLoad);

  useEffect(() => {
    if (asset.error) onAssetError?.(asset.error);
  }, [asset.error, onAssetError]);

  return <img {...props} ref={imageRef} src={asset.source || undefined} />;
}
