from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.models import User


class Client(models.Model):
    name = models.CharField(max_length=100, help_text='NOTA: Não pode existir o mesmo nome 2 vezes na base de dados!', verbose_name='Nome')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Cliente'
        constraints = [
            models.UniqueConstraint(fields=['name'], name='unique_name')
        ]
        verbose_name_plural = 'Clientes'


class Employee(models.Model):
    name = models.CharField(max_length=100, verbose_name='Nome')
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, help_text='Nome de utilizador das credenciais criadas para o empregado em questão.', verbose_name='Nome de utilizador')
    contract_hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="(CONTRATO) Valor hora aplicado a todos os serviços. Deixar vazio SE o empregado não estiver em contrato. NOTA: Se não estiver em contrato o valor terá que ser atribuído manualmente por bloco de trabalho criado!!!", verbose_name='Valor/Hora do contrato')

    def __str__(self):
        return self.name

    @property
    def has_contract(self):
        return self.contract_hourly_rate is not None

    class Meta:
        verbose_name = 'Empregado'
        verbose_name_plural = 'Empregados'


class EmployeeWorkAssignment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name='Empregado')
    work_block = models.ForeignKey('WorkBlock', on_delete=models.CASCADE, verbose_name='Bloco de trabalho')
    duration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Duration in hours for this employee", verbose_name='Duração (Que poderá ser alterada)')
    is_completed = models.BooleanField(default=False, verbose_name='Completou?')
    assigned_date = models.DateTimeField(auto_now_add=True, verbose_name='Data de atribuição')
    completed_date = models.DateTimeField(null=True, blank=True, verbose_name='Data da última marcação de concluído')
    receives_payment = models.BooleanField(default=True, help_text="Desativar caso o empregado não possa receber por este bloco", verbose_name='Recebe pagamento?')
    hourly_rate_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Se o empregado não estiver sujeito a contrato, este valor será aquele respetivo ao pagamento pelo trabalho feito no bloco. Deixar VAZIO nos empregados por contrato. NOTA: Se porventura um empregado por contrato tiver que receber um valor/hora diferente por este serviço, colocar um valor irá sobrepor o valor do contrato para este bloco (incluindo blocos criados pela opção CONSTANTE estar ativada aquando da criação do bloco de trabalho. Isto se o valor estiver a ser definido no menu de blocos de trabalho).", verbose_name='Valor/Hora a receber para o serviço atribuído')

    class Meta:
        unique_together = ['employee', 'work_block']

    def __str__(self):
        return f"{self.employee.name} - {self.work_block} - {self.duration}h"

    def get_employee_hourly_rate(self):
        """Get the hourly rate for this employee - override rate, contract rate, or workblock rate"""
        if self.hourly_rate_override is not None:
            return self.hourly_rate_override
        if self.employee.has_contract:
            return self.employee.contract_hourly_rate
        return 0

    def get_employee_payment(self):
        """Get the total payment for this employee for this workblock"""
        if not self.receives_payment:
            return 0
        return self.duration * self.get_employee_hourly_rate()

    def get_client_cost(self):
        """Get the cost charged to the client for this employee's work"""
        return self.duration * self.work_block.hourly_value




class WorkBlock(models.Model):
    name = models.CharField(max_length=200, blank=True, default="", verbose_name='Nome')
    localization = models.CharField(max_length=200, blank=True, default="", verbose_name='Morada')
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Cliente')
    start_time = models.TimeField(verbose_name='Hora de início')
    end_time = models.TimeField(verbose_name='Hora de fim')
    day_of_month = models.IntegerField(verbose_name='Dia do mês')
    month = models.IntegerField(default=timezone.now().month, verbose_name='Mês')
    year = models.IntegerField(default=timezone.now().year, verbose_name='Ano')
    employees_assigned = models.ManyToManyField(Employee, through=EmployeeWorkAssignment, related_name='assigned_blocks', blank=True, verbose_name='Empregados atribuídos')
    archived = models.BooleanField(default=False, verbose_name='Arquivado?')
    duration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Duração do serviço em valores decimais. Fórmula para converter tempos (H:M) em tempos decimais: HORAS + (MINUTOS / 60)", verbose_name='Duração')
    hourly_value = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Valor à hora a cobrar ao cliente", verbose_name='Valor/Hora')
    constant = models.BooleanField(default=False, help_text="Com esta opção ativada, a tarefa será replicada no mesmo dia da semana em todas as semanas até ao final do mês selecionado.", verbose_name='Constante?')

    def clean(self):
        if self.day_of_month < 1 or self.day_of_month > 31:
            raise ValidationError("Day of month must be between 1 and 31.")
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")

    def get_employees_concluded(self):
        """Get employees who have completed this work block"""
        return Employee.objects.filter(
            employeeworkassignment__work_block=self,
            employeeworkassignment__is_completed=True
        )

    def get_employee_duration(self, employee):
        """Get duration for specific employee or default duration"""
        try:
            assignment = EmployeeWorkAssignment.objects.get(work_block=self, employee=employee)
            return assignment.duration
        except EmployeeWorkAssignment.DoesNotExist:
            return self.duration

    def is_employee_completed(self, employee):
        """Check if employee has completed this work block"""
        try:
            assignment = EmployeeWorkAssignment.objects.get(work_block=self, employee=employee)
            return assignment.is_completed
        except EmployeeWorkAssignment.DoesNotExist:
            return False

    def __str__(self):
        return f"{self.name or 'WorkBlock'} {self.day_of_month}/{self.month}/{self.year} {self.start_time}-{self.end_time}"

    class Meta:
        verbose_name = 'Bloco de Trabalho'
        verbose_name_plural = 'Blocos de Trabalho'


class BonusPenalty(models.Model):
    BONUS = 'bonus'
    PENALTY = 'penalty'
    TYPE_CHOICES = [
        (BONUS, 'Bonus'),
        (PENALTY, 'Penalty'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='bonus_penalties', verbose_name='Empregado')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, verbose_name='Tipo')
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Valor a adicionar/subtrair do TOTAL do mês", verbose_name='Quantia')
    justification = models.TextField(help_text="Justificação para o bónus/penalização", verbose_name='Justificação')
    month = models.IntegerField(verbose_name='Mês')
    year = models.IntegerField(verbose_name='Ano')
    created_date = models.DateTimeField(auto_now_add=True, verbose_name='Data de criação')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Sancionador')

    class Meta:
        verbose_name = 'Bónus ou Penalização'
        verbose_name_plural = 'Bónus ou Penalizações'
        ordering = ['-created_date']

    def __str__(self):
        return f"{self.get_type_display()} for {self.employee.name}: €{self.amount} ({self.month}/{self.year})"

    @property
    def signed_amount(self):
        """Return amount with appropriate sign for display"""
        if self.type == self.PENALTY:
            return -abs(self.amount)
        return abs(self.amount)


class Changelog(models.Model):
    title = models.CharField(max_length=200, verbose_name='Título')
    description = models.TextField(verbose_name='Descrição')
    date_added = models.DateTimeField(auto_now_add=True, verbose_name='Data de adição')
    priority = models.IntegerField(default=0, verbose_name='Prioridade')
    users_seen = models.ManyToManyField(User, related_name='changelogs_seen', blank=True, verbose_name='Utilizadores que viram')

    class Meta:
        ordering = ['-date_added']

    def __str__(self):
        return f"{self.title} ({self.date_added.strftime('%d/%m/%Y')})"

    def mark_as_seen(self, user):
        """Mark this changelog as seen by the given user"""
        self.users_seen.add(user)
        self.save()

    @classmethod
    def get_unseen_changelogs(cls, user):
        """Get changelogs that haven't been seen by the given user"""
        return cls.objects.exclude(users_seen=user).order_by('-priority', '-date_added')
