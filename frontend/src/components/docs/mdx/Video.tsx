type Props = { src: string; caption?: string };

export function Video({ src, caption }: Props) {
  return (
    <figure className="my-4">
      <video controls preload="metadata" className="w-full rounded-card border border-line" src={src}>
        {caption}
      </video>
      {caption ? <figcaption className="mt-2 text-sm text-muted">{caption}</figcaption> : null}
    </figure>
  );
}
