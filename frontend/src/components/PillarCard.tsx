type PillarCardProps = {
  title: string;
  body: string;
};

export function PillarCard({ title, body }: PillarCardProps) {
  return (
    <article className="pillar-card">
      <h3>{title}</h3>
      <p>{body}</p>
    </article>
  );
}
