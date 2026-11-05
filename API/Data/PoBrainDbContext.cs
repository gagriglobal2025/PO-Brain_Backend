using Microsoft.EntityFrameworkCore;
using POBrain.API.Data.Entities;

namespace POBrain.API.Data;

public class PoBrainDbContext(DbContextOptions<PoBrainDbContext> options) : DbContext(options)
{
    public DbSet<User> Users => Set<User>();
    public DbSet<PasswordReset> PasswordResets => Set<PasswordReset>();
    public DbSet<Notification> Notifications => Set<Notification>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<User>(e =>
        {
            e.HasIndex(u => u.Username).IsUnique();
            e.HasIndex(u => u.Email).IsUnique();
        });

        modelBuilder.Entity<PasswordReset>(e =>
        {
            e.HasIndex(p => p.UserId).IsUnique();
            e.HasOne(p => p.User)
             .WithMany(u => u.PasswordResets)
             .HasForeignKey(p => p.UserId)
             .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<Notification>(e =>
        {
            e.ToTable("pobrain_notifications");
            e.HasKey(n => n.NotificationId);

            e.Property(n => n.NotificationId).HasColumnName("notification_id");
            e.Property(n => n.UserId).HasColumnName("user_id");
            e.Property(n => n.Type).HasColumnName("type");
            e.Property(n => n.Title).HasColumnName("title");
            e.Property(n => n.Message).HasColumnName("message");
            e.Property(n => n.IsRead).HasColumnName("is_read");
            e.Property(n => n.RelatedPoNumber).HasColumnName("related_po_number");
            e.Property(n => n.RelatedErrorId).HasColumnName("related_error_id");
            e.Property(n => n.CreatedAt).HasColumnName("created_at");
            e.Property(n => n.ReadAt).HasColumnName("read_at");

            e.HasIndex(n => n.UserId);
            e.HasIndex(n => new { n.UserId, n.IsRead });
            e.HasOne(n => n.User)
             .WithMany(u => u.Notifications)
             .HasForeignKey(n => n.UserId)
             .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
